# Grimoire RAG Pipeline Design

## Overview

Add a RAG (Retrieval-Augmented Generation) pipeline to Grimoire that enables rule queries, sourcebook lookups, and campaign world state searches. This design consolidates all compute into the homelab cluster, eliminating Cloud Run and GCS in favor of in-cluster services (SeaweedFS, NATS JetStream) with only Firestore and Gemini API remaining as GCP dependencies.

## Goals

- DM and players can query ingested sourcebook content (rules, monsters, spells, items, lore) and receive grounded answers with book + page citations.
- DM can query campaign world state (NPCs, locations, factions) in the same search. Players cannot see DM-only campaign data.
- Sourcebook PDFs are stored locally on SeaweedFS. Only processed chunks + embeddings are written to Firestore.
- Ingestion is replayable via NATS JetStream. Re-ingesting a book (new chunking strategy, updated embeddings) is a stream purge + replay with idempotent Firestore upserts.

## Architecture

### GCP Dependencies (reduced)

| GCP Service | Purpose | Replaceable? |
|-------------|---------|-------------|
| Firestore | Game state + sourcebook vector search (`FindNearest`) | Not easily — Firestore's native vector search avoids running a separate vector DB |
| Gemini API | `text-embedding-005` (768-dim embeddings) + Gemini Flash (RAG answers) | Could swap LLM providers, but Gemini pricing is optimal for this scale |
| ~~Cloud Run~~ | Eliminated | Replaced by in-cluster API Service |
| ~~GCS~~ | Eliminated | Replaced by SeaweedFS |

### Service Architecture

```
Homelab K8s Cluster
├── WS Gateway         (Go)    WebSocket relay, presence, voice status. Redis pub/sub.
├── API Service         (Go)    REST CRUD + RAG query handler. Firestore + Gemini API.
├── Chunk Writer        (Go)    NATS JetStream consumer → Firestore upserts.
├── Ingest Job          (Python) PDF → chunk → embed → NATS publish. K8s Job, on-demand.
├── Frontend            (React)  Static build via Nginx.
├── Redis                        Pub/sub for WS Gateway multi-replica relay.
├── NATS JetStream               Persistent stream for ingested chunks.
└── SeaweedFS                    S3-compatible storage for source PDFs.
```

### Service Responsibilities

| Service | Language | Responsibilities | Cluster Dependencies | GCP Dependencies |
|---------|----------|-----------------|---------------------|-----------------|
| WS Gateway | Go | WebSocket relay, presence, voice status broadcast | Redis | None |
| API Service | Go | REST CRUD (campaigns, characters, encounters, dice, feed), RAG query handler | None | Firestore, Gemini API |
| Chunk Writer | Go | NATS consumer, upsert `sourcebook_chunks` to Firestore | NATS | Firestore |
| Ingest Job | Python | PDF parse + chunk + embed, publish to NATS | SeaweedFS (S3), NATS | Gemini API (embedding) |
| Frontend | React | Static build, REST + WebSocket client | API Service, WS Gateway | None |

### GCP Authentication

All services that need GCP access use a single service account via Application Default Credentials (ADC):

1. Service account: `grimoire-gateway@grimoire-prod.iam.gserviceaccount.com`
2. Roles: `roles/datastore.user` (Firestore), `roles/aiplatform.user` (Gemini API)
3. JSON key stored in 1Password: `vaults/k8s-homelab/items/grimoire`, field: `gcp_service_account`
4. Mounted as a file in pods via the existing `OnePasswordItem` CRD
5. `GOOGLE_APPLICATION_CREDENTIALS` env var points to the mounted file
6. Replaces the existing `GOOGLE_API_KEY` env var — both Firestore and Gemini clients use ADC

## RAG Query Flow

### Sourcebook Queries (all users)

```
POST /api/rag/query
{
  "query": "Does sneak attack work with ranged spells?",
  "content_type": "rule",      // optional filter
  "books": ["PHB"],            // optional filter
  "edition": "2024"            // optional filter
}
```

Handler flow:
1. Embed query via `text-embedding-005` (768-dim vector)
2. `FindNearest` on `sourcebook_chunks` collection (cosine distance, top-5)
3. Apply metadata filters: `content_type`, `source_book`, `edition`
4. Filter by `audience`: always exclude `dm_only` chunks for non-DM users
5. Assemble context, send to Gemini Flash with system prompt:
   > "Answer this D&D question using only the provided context. Cite source book and page for each claim."
6. Return structured response

### Campaign + Sourcebook Queries (DM only)

```
POST /api/rag/query
{
  "query": "What does Vex know about the Shadow Thieves?",
  "campaign_id": "abc123"
}
```

Additional handler steps (when `campaign_id` provided and user is DM):
1. Keyword search NPCs, locations, factions by name/description substring match
2. Include matching campaign entities in the Gemini Flash context alongside sourcebook chunks
3. Campaign context is never returned to non-DM users

### Response Format

```json
{
  "query": "Does sneak attack work with ranged spells?",
  "answer": "No. Sneak Attack requires a finesse or ranged *weapon* attack, not a spell attack...",
  "citations": [
    {
      "source_book": "PHB",
      "page": 96,
      "section": "Sneak Attack",
      "content_type": "rule",
      "relevance": 0.94,
      "text": "Beginning at 1st level, you know how to strike subtly..."
    }
  ],
  "campaign_context": [
    {
      "type": "npc",
      "name": "Vex the Rogue",
      "summary": "Level 5 Arcane Trickster, frequently asks about spell-sneak attack interactions"
    }
  ]
}
```

## RAG Ingestion Pipeline

### Flow

```
Upload PDF to SeaweedFS (s3://grimoire-sourcebooks/phb.pdf)
    ↓
Run Ingest Job (K8s Job)
  → Read PDF from SeaweedFS via S3 API (in-cluster)
  → pymupdf4llm: layout-aware text extraction
  → Chunk by content type (see Chunking Strategy below)
  → Batch embed via Gemini text-embedding-005
  → Publish each chunk to NATS stream: grimoire.chunks.<source_book>
    ↓
Chunk Writer (always-running consumer)
  → Subscribes to grimoire.chunks.>
  → Upserts each chunk to Firestore sourcebook_chunks collection
  → Doc ID = deterministic hash (source_book + page + section + content_type)
```

### NATS JetStream Configuration

```
Stream:    GRIMOIRE_CHUNKS
Subjects:  grimoire.chunks.>
Retention: Limits
Storage:   File
Replicas:  1
```

Subject naming: `grimoire.chunks.<source_book>` (e.g., `grimoire.chunks.phb`, `grimoire.chunks.mm`)

Replaying a book: purge the subject (`grimoire.chunks.phb`), re-run the ingest job. The Chunk Writer receives new messages and upserts replace old Firestore docs via deterministic doc IDs.

### Chunking Strategy

#### By Content Type

| Content Type | Strategy | Rationale |
|-------------|----------|-----------|
| Monster stat block | One chunk per monster, complete stat block | Self-contained units; splitting loses context |
| Spell | One chunk per spell (description + at higher levels) | Self-contained; cross-reference via school/level metadata |
| Magic item | One chunk per item (properties + description) | Self-contained |
| Class/race feature | One chunk per feature (Extra Attack, Sneak Attack, Darkvision) | Discrete mechanical units |
| Rule | Hierarchical chunking: chapter → section → subsection, 512-token overlapping windows, parent section title preserved in chunk | Rules reference surrounding context; hierarchical structure preserves "Chapter 9: Combat > Melee Attacks > Opportunity Attacks" lineage |
| Lore | One chunk per topic/entity (location, faction, deity, NPC) with cross-references | Enables entity-level retrieval; cross-references link related lore |
| Encounter/adventure | One chunk per encounter or scene, with location + difficulty metadata | Enables DM prep queries like "find a CR 3 forest encounter" |

#### Hierarchical Chunking for Rules

Rules sections benefit from preserving their position in the document hierarchy. Each rule chunk includes a `section_path` field:

```
section_path: "Part 2: Playing the Game > Chapter 9: Combat > Making an Attack > Melee Attacks > Opportunity Attacks"
```

This allows the RAG prompt to include parent context without duplicating full parent text in every chunk. The Gemini Flash system prompt can reference section paths to ground its answers in the document structure.

Overlapping windows (512 tokens, 64-token overlap) ensure that concepts spanning chunk boundaries are captured in at least one chunk.

### Metadata Per Chunk

Every chunk stored in `sourcebook_chunks` carries the following metadata:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The chunk text content |
| `embedding` | vector(768) | `text-embedding-005` vector |
| `source_book` | string | Source book identifier (e.g., "PHB", "MM", "DMG") |
| `page` | int | Page number in source PDF |
| `section` | string | Section title |
| `section_path` | string | Full hierarchical path (for rules) |
| `content_type` | string | `rule` \| `stat_block` \| `lore` \| `item` \| `spell` \| `encounter` \| `npc` \| `location` \| `adventure` |
| `audience` | string | `dm_only` \| `player_safe` \| `spoiler` |
| `edition` | string | `2014` \| `2024` \| `both` |
| `metadata` | map | Type-specific fields: CR, level, school, rarity, etc. |

#### Audience Classification

- **player_safe**: General rules, publicly known spells/items/monsters. Safe to return to any user.
- **dm_only**: DM-facing content like adventure text, encounter setups, hidden NPC motivations, trap details. Never returned to non-DM queries.
- **spoiler**: Content that could spoil plot (monster weaknesses in adventure context, treasure locations). Filtered for players, shown to DM.

The ingest pipeline classifies audience based on content type and source location:
- Monster stat blocks from the Monster Manual → `player_safe` (public knowledge)
- Monster entries from an adventure module → `spoiler` (context-specific)
- Adventure narrative text → `dm_only`
- Rules from PHB/DMG → `player_safe`
- DMG-specific advice sections → `dm_only`

### Firestore Vector Index

```
Collection: sourcebook_chunks
Field path: embedding
Dimensions: 768
Distance measure: COSINE
```

## Helm Chart Changes

### WS Gateway (simplified)

Remove: `GOOGLE_API_KEY`, Firestore-related env vars (if any were planned).
Keep: `REDIS_ADDR`, `REDIS_PASSWORD`, `CF_ACCESS_TEAM`.
The WS Gateway becomes a pure WebSocket relay with no GCP dependencies.

### API Service (new deployment)

New deployment in the grimoire Helm chart:

- Image: `ghcr.io/jomcgi/homelab/services/grimoire-api`
- Env vars: `GCP_PROJECT_ID`, `FIRESTORE_DATABASE`, `CF_ACCESS_TEAM`, `GOOGLE_APPLICATION_CREDENTIALS`
- Volume mount: GCP service account JSON key from 1Password secret
- Service: ClusterIP on port 8080
- Routes: all `/api/*` REST endpoints + `POST /api/rag/query`

### Chunk Writer (new deployment)

New deployment in the grimoire Helm chart:

- Image: `ghcr.io/jomcgi/homelab/services/grimoire-chunk-writer`
- Env vars: `NATS_URL`, `GCP_PROJECT_ID`, `FIRESTORE_DATABASE`, `GOOGLE_APPLICATION_CREDENTIALS`
- Volume mount: GCP service account JSON key from 1Password secret
- No service (no inbound traffic — it only consumes from NATS)

### Ingest Job (new job template)

Job template in the grimoire Helm chart:

- Image: `ghcr.io/jomcgi/homelab/services/grimoire-ingest`
- Env vars: `NATS_URL`, `SEAWEEDFS_ENDPOINT`, `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `PDF_PATH`, `SOURCE_BOOK`
- Volume mount: GCP service account JSON key from 1Password secret
- `restartPolicy: Never`, `backoffLimit: 1`

### Frontend Nginx

Update Nginx config to proxy `/api/*` to the API Service instead of an external Cloud Run endpoint (if that was configured). Since the API Service runs in-cluster, this is a simple `proxy_pass` to `http://grimoire-api:8080`.

## Migration Path

1. Create GCP service account with Firestore + Gemini API access
2. Store JSON key in 1Password
3. Create Firestore vector index on `sourcebook_chunks`
4. Build and deploy API Service (absorb existing Cloud Run API code + add RAG handler)
5. Build and deploy Chunk Writer (NATS consumer + Firestore upserts)
6. Build Ingest Job image (Python)
7. Update WS Gateway to remove Firestore/Gemini dependencies (simplify)
8. Update Frontend Nginx proxy config
9. Upload a sourcebook PDF to SeaweedFS, run ingest job, verify end-to-end
10. Decommission Cloud Run services in GCP
