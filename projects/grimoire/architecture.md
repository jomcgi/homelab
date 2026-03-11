# GRIMOIRE

### A self-hosted D&D campaign manager with AI-assisted DMing

---

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [System Architecture](#system-architecture)
4. [Voice Pipeline](#voice-pipeline)
5. [Data Model](#data-model)
6. [Service Specifications](#service-specifications)
7. [GCP Serverless Services](#gcp-serverless-services)
8. [RAG Pipeline](#rag-pipeline)
9. [Classification System](#classification-system)
10. [UI Specification](#ui-specification)
11. [Kubernetes Deployment](#kubernetes-deployment)
12. [GCP Bootstrap](#gcp-bootstrap)
13. [Security Model](#security-model)
14. [Cost Estimate](#cost-estimate)
15. [Implementation Phases](#implementation-phases)

---

## Overview

Grimoire is a campaign manager for tabletop RPGs — primarily D&D 5e — that combines real-time multiplayer session management with AI-powered voice transcription, rule lookup, and context tracking. The system is designed for a small group of friends (3-6 players + DM) playing regular sessions.

The architecture splits across two environments:

- **Homelab Kubernetes cluster**: Real-time communication, frontend hosting, voice proxy, and the thin API relay. Only credential: a Gemini API key synced from 1Password via External Secrets Operator, consumed server-side by the WebSocket gateway.
- **GCP serverless**: All persistence (Firestore), all intelligence (Gemini), all storage (Cloud Storage). Pay-per-request with no idle cost.

GCP infrastructure is provisioned once via authenticated CLI scripts from the operator's laptop. The homelab cluster syncs a Gemini API key from 1Password via External Secrets Operator, used server-side by the WebSocket gateway — it is never exposed to browsers.

**Reference UI**: `services/grimoire/example-ui.jsx` — interactive React component showing all four views (DM Live, DM Prep, Player Live, Player Character).

---

## Design Principles

**No persistent GCP servers.** Every GCP service bills per-request or per-document. Nothing runs when nobody is playing. Monthly cost target: under $3 for 4 sessions/month.

**No secrets in the browser.** Infrastructure provisioning happens from an authenticated laptop via `gcloud`. The Gemini API key is stored in 1Password and synced to the cluster via External Secrets Operator — consumed only by the WebSocket gateway, never exposed to browsers. All browser traffic is authenticated via Cloudflare Access (SSO).

**Voice is a first-class input.** Players speak naturally. Browser-side Voice Activity Detection (VAD) captures speech segments and streams them to the WebSocket gateway, which proxies audio to Gemini Live for transcription, classification, and tool calls. No separate STT pipeline. Silent audio is never sent, keeping costs low.

**Players never see the machinery.** Classification tags, confidence scores, RAG chunks, token budgets, and context management are DM-only. Players see a clean narrative feed.

**GitOps for cluster resources, scripts for cloud resources.** Homelab workloads deploy via ArgoCD. GCP resources are static infrastructure created once via Makefile.

---

## System Architecture

```mermaid
flowchart TB
    subgraph Browser["Browser — per player"]
        direction LR
        UI["Grimoire UI<br/><i>React + TypeScript</i>"]
        VAD["VAD<br/><i>Voice Activity Detection</i>"]
        AppWS["Grimoire WS<br/><i>Game state + audio</i>"]
    end

    subgraph CF["Cloudflare"]
        CFAccess["Cloudflare Access<br/><i>SSO / identity-aware proxy</i>"]
        CFTunnel["Cloudflare Tunnel<br/><i>grimoire.yourdomain.com</i>"]
    end

    subgraph GCP["GCP — Serverless / Pay-per-request"]
        direction TB
        subgraph AI["AI Services"]
            GemLive["Gemini 2.0 Flash Live API<br/>· Transcription<br/>· Classification<br/>· Tool calls"]
            GemFlash["Gemini 2.0 Flash<br/>· RAG answers<br/>· Session summaries<br/>· Encounter generation"]
            GemEmbed["text-embedding-005<br/>· 768-dim vectors<br/>· $0.15/1M tokens"]
        end
        subgraph Data["Data & Storage"]
            Firestore[("Firestore<br/>· Game state<br/>· Vector search<br/>· Real-time sync")]
            GCS[("Cloud Storage<br/>· Source PDFs<br/>· Extracted art")]
        end
        subgraph Compute["Compute"]
            CloudRunAPI["Cloud Run — API<br/>· Go binary<br/>· Scales to zero"]
            CloudRunIngest["Cloud Run — Ingest<br/>· PDF pipeline<br/>· One-time per book"]
        end
    end

    subgraph Homelab["Homelab K8s Cluster"]
        direction TB
        FE["Frontend<br/><i>Static React via Nginx</i>"]
        WSGateway["WebSocket Gateway<br/><i>Voice proxy + game relay</i>"]
        Redis[("Redis<br/><i>Pub/sub + ephemeral state</i>")]
    end

    UI --> VAD
    VAD -->|"Speech segments"| AppWS
    AppWS <-->|"Authenticated"| CFAccess
    CFAccess <--> CFTunnel
    CFTunnel <--> WSGateway
    WSGateway <-->|"Audio proxy<br/>(per-player sessions)"| GemLive
    GemLive -->|"Tool calls"| CloudRunAPI
    GemLive -->|"Transcripts + classifications"| WSGateway
    WSGateway <--> Redis
    CloudRunAPI <--> Firestore
    CloudRunAPI -->|"RAG query"| GemEmbed
    GemEmbed --> Firestore
    Firestore -->|"Top-k chunks"| GemFlash
    GemFlash -->|"Answer + citations"| CloudRunAPI
    GCS --> CloudRunIngest
    CloudRunIngest -->|"Chunks + vectors"| Firestore
    CloudRunIngest -->|"Art assets"| GCS
    CFTunnel --> FE

    style Browser fill:#f8f8f6,stroke:#1a1a1a,color:#1a1a1a
    style CF fill:#fff3e0,stroke:#f97316,color:#1a1a1a
    style GCP fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    style Homelab fill:#f0fdf4,stroke:#16a34a,color:#1a1a1a
    style AI fill:#d2e3fc,stroke:#4285f4,color:#1a1a1a
    style Data fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    style Compute fill:#d2e3fc,stroke:#4285f4,color:#1a1a1a
```

### Data Flow Summary

| Flow               | Path                                                                                         | Latency Target |
| ------------------ | -------------------------------------------------------------------------------------------- | -------------- |
| Voice → transcript | Browser (VAD) → WS Gateway → Gemini Live → WS Gateway → all clients                          | < 800ms        |
| Dice roll          | Browser → WS Gateway → Cloud Run API → Firestore → all clients                               | < 200ms        |
| Rule lookup        | Voice/UI → Cloud Run API → embed → Firestore vector search → Gemini Flash → DM context panel | < 2s           |
| Chat message       | Browser → WS Gateway → Cloud Run API → Firestore → all clients (real-time listener)          | < 300ms        |
| HP update          | DM UI → Cloud Run API → Firestore → all clients                                              | < 200ms        |
| Lore propagation   | Classification → Cloud Run API → Firestore lore collection → player real-time listener       | < 1s           |

---

## Voice Pipeline

Each player's browser captures audio via the Web Audio API with client-side Voice Activity Detection (VAD). When speech is detected, PCM audio segments are streamed over the single WebSocket connection to the homelab gateway. The gateway maintains one Gemini Live session per player and proxies audio server-side — the Gemini API key never leaves the cluster.

### Voice Activity Detection (VAD)

Browser-side VAD ensures silence is never sent to Gemini, which bills at ~25 tokens/second regardless of content. This reduces audio costs by ~70% compared to always-on streaming.

**Implementation:** Use a lightweight VAD library (e.g., `@ricky0123/vad-web` — a Silero VAD ONNX model running in a Web Worker). The browser captures PCM audio at 16kHz 16-bit, VAD segments speech, and only active speech frames are sent to the gateway.

```
Browser mic → Web Audio API → VAD (Silero ONNX) → speech segments → WS Gateway
                                    ↓
                              silence → dropped (no cost)
```

### Data Flow

```mermaid
sequenceDiagram
    participant P as Player Browser
    participant WS as WS Gateway (Homelab)
    participant GL as Gemini Live API
    participant API as Cloud Run API
    participant FS as Firestore
    participant DM as DM Browser

    Note over P: Player speaks: "Does sneak attack<br/>work with a ranged spell?"

    P->>P: VAD detects speech
    P->>WS: Audio segment (PCM via WebSocket)
    WS->>GL: Proxy audio to player's Gemini session
    GL->>GL: Transcribe + classify

    Note over GL: Classification: rules_question<br/>Confidence: 0.91

    GL->>API: Tool call: lookup_rule("sneak attack ranged spell")
    API->>FS: Vector search (sourcebook_chunks)
    FS-->>API: Top-5 chunks + metadata
    API->>GL: Rule text + citations
    GL-->>WS: Structured response (transcript + classification + RAG result)

    WS->>FS: Write to feed subcollection
    WS->>DM: Relay feed event (WebSocket)
    WS->>P: Relay feed event (WebSocket)

    Note over DM: DM sees: transcript with 📖 Rules pill,<br/>RAG result auto-surfaces in context panel
```

### Gemini Live Session Management

The WebSocket gateway maintains one Gemini Live session per connected player. Each session is initialized with a system prompt:

```
You are a D&D session transcription assistant.

CONTEXT:
- Campaign: {campaign_name}
- Current encounter: {encounter_description}
- Active characters: {character_list}
- DM name: {dm_name}
- Speaker: {player_name} ({character_name})

CLASSIFY every utterance into exactly one category:
- ic_action: In-character action declaration ("I attack the goblin")
- ic_dialogue: In-character speech ("Hail, innkeeper!")
- rules_question: Rules inquiry ("Does that provoke an opportunity attack?")
- dm_narration: DM describing scenes or NPC dialogue
- dm_ruling: DM making a rules call
- table_talk: Out-of-character chatter ("Anyone want pizza?")

TOOLS AVAILABLE:
- lookup_rule(query: string) → Search sourcebooks for rules
- roll_dice(formula: string) → Roll dice (e.g., "2d6+3", "1d20adv")
- update_hp(character: string, delta: int) → Adjust HP

Return structured JSON for each utterance:
{
  "transcript": "...",
  "classification": "ic_action",
  "confidence": 0.94,
  "tool_calls": [...]
}
```

### Session Reconnection

Gemini Live sessions are capped at ~10-15 minutes (audio-only). For a 4-hour D&D session, the gateway must reconnect ~16-24 times per player. The gateway handles this transparently:

1. Gemini sends a "going away" notification before session expiry
2. Gateway opens a new session with the same system prompt + recent context summary
3. Audio from the browser continues uninterrupted — reconnection is invisible to the player
4. A rolling buffer of recent transcripts (~2 minutes) is replayed into the new session for continuity

### Speaker Identification

No diarization needed. Each player has their own Gemini Live session on the gateway, so every audio chunk arrives pre-tagged with user identity. The gateway tags all Gemini responses with the originating player ID.

### Rate Limits

Gemini Live API concurrent session limits by tier:

| Tier       | Concurrent Sessions | Requirement                  |
| ---------- | ------------------- | ---------------------------- |
| Free       | 3                   | None                         |
| **Tier 1** | **~50**             | **Enable billing (instant)** |
| Tier 2     | ~1,000              | $250+ cumulative spend       |

**Grimoire requires Tier 1** (6 concurrent sessions for 5 players + DM). Upgrading is instant — just enable billing on the GCP project. New accounts receive $300 in free credits.

---

## Data Model

All persistent state lives in Firestore. Collections are organized by campaign.

```mermaid
erDiagram
    CAMPAIGN ||--o{ SESSION : "has many"
    CAMPAIGN ||--o{ CHARACTER : "has many"
    CAMPAIGN ||--o{ NPC : "has many"
    CAMPAIGN ||--o{ LOCATION : "has many"
    CAMPAIGN ||--o{ FACTION : "has many"
    SESSION ||--o{ ENCOUNTER : "has many"
    SESSION ||--o{ FEED_EVENT : "has many"
    SESSION ||--o{ SESSION_NOTE : "has one"
    ENCOUNTER ||--o{ ENCOUNTER_MONSTER : "has many"
    CHARACTER ||--o{ LORE_ENTRY : "knows many"
    CHARACTER ||--o{ INVENTORY_ITEM : "carries many"

    CAMPAIGN {
        string id PK
        string name
        string system "e.g. dnd5e"
        string dm_user_id
        map world_state
        timestamp created_at
    }

    SESSION {
        string id PK
        string campaign_id FK
        int session_number
        string status "planning|active|paused|completed"
        timestamp started_at
        timestamp ended_at
    }

    CHARACTER {
        string id PK
        string campaign_id FK
        string user_id
        string name
        string race
        string class
        int level
        int hp
        int max_hp
        int ac
        map abilities "str,dex,con,int,wis,cha"
        array conditions
        array spell_slots
        string color "player color in UI"
    }

    FEED_EVENT {
        string id PK
        string session_id FK
        string speaker_id
        string source "voice|typed|roll|system"
        string classification
        float confidence
        string text
        map roll "formula, result, type"
        string private_to "null or player_id"
        bool rag_triggered
        timestamp created_at
    }

    ENCOUNTER {
        string id PK
        string session_id FK
        string name
        string status "planned|active|completed"
        int round
        string current_turn_id
        array initiative_order
        string terrain
    }

    ENCOUNTER_MONSTER {
        string id PK
        string encounter_id FK
        string name
        int hp
        int max_hp
        int ac
        int initiative
        string cr
        array conditions
        string source_ref "MM p.249"
    }

    LORE_ENTRY {
        string id PK
        string character_id FK
        string campaign_id FK
        string fact
        string source "session number or method"
        bool is_new
        timestamp revealed_at
    }

    INVENTORY_ITEM {
        string id PK
        string character_id FK
        string name
        string detail
        bool equipped
        float weight
    }

    SESSION_NOTE {
        string id PK
        string session_id FK
        string summary "LLM-generated"
        array world_state_updates
        timestamp generated_at
    }

    NPC {
        string id PK
        string campaign_id FK
        string name
        string description
        string location_id FK
        string faction_id FK
        string disposition
    }

    LOCATION {
        string id PK
        string campaign_id FK
        string name
        string description
        string parent_location_id FK
    }

    FACTION {
        string id PK
        string campaign_id FK
        string name
        string description
        string disposition
    }
```

### Session State Machine

```mermaid
stateDiagram-v2
    [*] --> planning : POST /sessions
    planning --> active : POST /sessions/:id/start
    active --> paused : POST /sessions/:id/pause
    paused --> active : POST /sessions/:id/resume
    active --> completed : POST /sessions/:id/end
    paused --> completed : POST /sessions/:id/end
    completed --> [*]
```

| Transition           | Trigger                         | Side Effects                                                      |
| -------------------- | ------------------------------- | ----------------------------------------------------------------- |
| `→ planning`         | DM creates session              | Session number auto-incremented, encounter slots available        |
| `planning → active`  | DM starts session               | `started_at` set, Gemini Live sessions opened, feed begins        |
| `active → paused`    | DM pauses (break, end of night) | Gemini Live sessions closed, voice bar shows "Paused"             |
| `paused → active`    | DM resumes                      | Gemini Live sessions re-opened, feed resumes                      |
| `active → completed` | DM ends session                 | `ended_at` set, summary generation triggered, world state updated |
| `paused → completed` | DM ends from paused state       | Same as above                                                     |

**Invariants:**

- A campaign can have at most one `active` or `paused` session at a time
- `completed` is terminal — sessions cannot be re-opened (start a new session instead)
- `planning` sessions can be deleted (draft encounters not yet played)
- Feed events can only be written to `active` sessions

### Encounter State Machine

```mermaid
stateDiagram-v2
    [*] --> planned : POST /encounters (during session planning or live)
    planned --> active : POST /encounters/:id/start
    active --> completed : POST /encounters/:id/end
    completed --> [*]
```

| Transition           | Side Effects                                                    |
| -------------------- | --------------------------------------------------------------- |
| `→ planned`          | Monsters added, initiative not yet rolled                       |
| `planned → active`   | Initiative rolled/entered, round set to 1, turn tracking begins |
| `active → completed` | Final round recorded, XP/loot available for summary             |

**Invariants:**

- A session can have at most one `active` encounter at a time
- Multiple `planned` encounters can exist (DM prep queue)
- `completed` is terminal

### Firestore Collection Structure

```
campaigns/
  {campaign_id}/
    characters/
      {character_id}/
        inventory/
          {item_id}
        lore/
          {lore_id}
    sessions/
      {session_id}/
        feed/
          {event_id}
        encounters/
          {encounter_id}/
            monsters/
              {monster_id}
        notes/
          {note_id}
    npcs/
      {npc_id}
    locations/
      {location_id}
    factions/
      {faction_id}

sourcebook_chunks/
  {chunk_id}
    - text: string
    - embedding: vector(768)
    - source_book: string
    - page: int
    - section: string
    - content_type: "monster" | "spell" | "item" | "rule" | "class" | "race"
    - metadata: map (CR, level, school, etc.)

art_assets/
  {asset_id}
    - gcs_uri: string
    - source_book: string
    - page: int
    - context_tag: string
    - description: string (Gemini Vision generated)
```

### Firestore Vector Index

```
Collection: sourcebook_chunks
Field path: embedding
Dimensions: 768
Distance measure: COSINE
```

Query pattern for RAG:

```go
vectorQuery := client.Collection("sourcebook_chunks").
    FindNearest("embedding", queryVector,
        firestore.DistanceMeasureCosine,
        &firestore.FindNearestOptions{Limit: 5}).
    Where("content_type", "==", "rule").
    Where("source_book", "in", allowedBooks)
```

---

## Service Specifications

### Cloud Run — grimoire-api (Go)

Single Go binary serving HTTP. Scales to zero. Handles all game logic and acts as the bridge between clients and Firestore/Gemini.

```mermaid
flowchart LR
    subgraph API["grimoire-api — Cloud Run"]
        direction TB
        Campaign["Campaign<br/>· CRUD campaigns<br/>· Session state machine<br/>· World state"]
        Character["Character<br/>· Creation wizard<br/>· Sheet management<br/>· Level-up flow<br/>· PDF export"]
        Dice["Dice<br/>· Roll parsing<br/>· 2d6+3, 4d6kh3, 1d20adv<br/>· Group/private rolls<br/>· Roll history"]
        Feed["Feed<br/>· Unified timeline<br/>· Classification storage<br/>· Visibility filtering"]
        Lore["Lore<br/>· Per-player knowledge<br/>· Auto-propagation<br/>· Source tracking"]
        RAG["RAG Gateway<br/>· Query embedding<br/>· Firestore vector search<br/>· Gemini Flash answer<br/>· Citation formatting"]
        Encounter["Encounter<br/>· Initiative tracking<br/>· Monster management<br/>· HP/condition updates<br/>· Round advancement"]
    end

    Campaign --- Character
    Campaign --- Encounter
    Encounter --- Dice
    Feed --- Lore
    RAG --- Feed

    style API fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
```

**Runtime requirements:**

- Go 1.22+
- Dependencies: `cloud.google.com/go/firestore`, `github.com/google/generative-ai-go/genai`, `cloud.google.com/go/storage`
- Environment variables: `GCP_PROJECT_ID`, `FIRESTORE_DATABASE`, `CF_ACCESS_TEAM`
- Authentication: Cloud Run service account (Firestore/GCS/Gemini Flash), Cloudflare Access JWT validation
- Memory: 256MB (Cloud Run minimum)
- CPU: 1 vCPU
- Concurrency: 80 (default)
- Min instances: 0 (scale to zero)
- Max instances: 2 (plenty for 5 players)
- Startup time: < 2s (Go cold start)

**API Routes:**

```
# Campaigns
GET    /api/campaigns
POST   /api/campaigns
GET    /api/campaigns/:id
PATCH  /api/campaigns/:id

# Sessions
GET    /api/campaigns/:id/sessions
POST   /api/campaigns/:id/sessions
PATCH  /api/campaigns/:cid/sessions/:sid
POST   /api/campaigns/:cid/sessions/:sid/start
POST   /api/campaigns/:cid/sessions/:sid/pause
POST   /api/campaigns/:cid/sessions/:sid/resume
POST   /api/campaigns/:cid/sessions/:sid/end

# Characters
GET    /api/campaigns/:id/characters
POST   /api/campaigns/:id/characters
GET    /api/characters/:id
PATCH  /api/characters/:id
GET    /api/characters/:id/lore
POST   /api/characters/:id/lore

# Encounters
POST   /api/sessions/:sid/encounters
PATCH  /api/encounters/:id
POST   /api/encounters/:id/next-turn
POST   /api/encounters/:id/end-round
PATCH  /api/encounters/:eid/monsters/:mid

# Dice
POST   /api/roll                    { formula, context, private }
GET    /api/sessions/:sid/rolls

# Feed
GET    /api/sessions/:sid/feed      ?classification=&speaker=&after=
POST   /api/sessions/:sid/feed      (write transcript/chat event)
PATCH  /api/feed/:id/reclassify     { new_classification }

# RAG
POST   /api/rag/query               { query, content_type?, books? }
GET    /api/rag/context/:session_id  (active context chunks)
POST   /api/rag/pin/:chunk_id
DELETE /api/rag/pin/:chunk_id

# Summaries
POST   /api/sessions/:sid/summarize  (end-of-session LLM summary)
```

### Cloud Run — grimoire-ingest (Python)

Runs as a Cloud Run Job (not a service). Triggered manually or via `gcloud` when a new sourcebook is added.

**Pipeline:**

```mermaid
flowchart LR
    PDF["PDF in<br/>Cloud Storage"] --> Parse["pymupdf4llm<br/>Layout-aware<br/>text extraction"]
    Parse --> Chunk["Chunker<br/>· Entities: monsters, spells, items<br/>· Rules: 512-token overlapping<br/>· Section headers preserved"]
    Parse --> Art["Art Extractor<br/>· Identify images<br/>· Export to GCS<br/>· Gemini Vision caption"]
    Chunk --> Embed["text-embedding-005<br/>Batch embed<br/>768-dim vectors"]
    Embed --> Store["Firestore<br/>sourcebook_chunks<br/>with vectors + metadata"]
    Art --> ArtStore["Cloud Storage<br/>+ Firestore metadata"]

    style PDF fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    style Store fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    style ArtStore fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
```

**Runtime requirements:**

- Python 3.12+
- Dependencies: `pymupdf4llm`, `google-cloud-firestore`, `google-cloud-storage`, `google-generativeai`
- Memory: 1GB (PDF processing)
- CPU: 2 vCPU
- Timeout: 15 minutes
- Execution: On-demand job, not always-running

**Chunking strategy by content type:**

| Content Type | Chunking Strategy                | Example                                  |
| ------------ | -------------------------------- | ---------------------------------------- |
| Monster      | One chunk per monster stat block | Owlbear: full stat block as single chunk |
| Spell        | One chunk per spell              | Fireball: description + at higher levels |
| Item         | One chunk per magic item         | Bag of Holding: properties + description |
| Class/Race   | One chunk per feature            | Extra Attack, Sneak Attack, Darkvision   |
| Rule         | 512-token overlapping windows    | Combat rules, spellcasting rules         |

### WebSocket Gateway (Homelab)

Central real-time hub running in the homelab cluster. Serves two roles: (1) game state relay for all clients, and (2) server-side Gemini Live proxy for voice transcription. The Gemini API key lives here — never in the browser.

**Responsibilities:**

- Maintain one Gemini Live WebSocket session per connected player
- Receive VAD-filtered PCM audio from browsers, proxy to Gemini Live
- Relay Gemini transcription/classification results back to all clients
- Handle Gemini Live session reconnection (every ~10-15 min) transparently
- Broadcast game state events (dice rolls, encounters, feed events)
- Track voice/presence status

**Runtime requirements:**

- Go (`nhooyr.io/websocket` for client connections, Gemini Live client for upstream)
- Redis for pub/sub across replicas
- Memory: 256MB (increased for Gemini session buffers)
- CPU: 200m
- Replicas: 1 (sufficient for 5-6 concurrent connections)
- Environment: `GOOGLE_API_KEY` from OnePasswordItem (1Password `grimoire` item)

**Event types (browser ↔ gateway):**

```typescript
type WSEvent =
  | { type: "audio_chunk"; data: ArrayBuffer } // browser → gateway (VAD-filtered PCM)
  | { type: "voice_status"; speaker_id: string; speaking: boolean }
  | { type: "transcript"; event: TranscriptEvent } // gateway → browsers (from Gemini)
  | { type: "feed_event"; event: FeedEvent }
  | { type: "roll_result"; roll: RollResult }
  | { type: "encounter_update"; encounter: Encounter }
  | { type: "dm_correction"; event_id: string; new_classification: string }
  | { type: "presence"; player_id: string; status: "online" | "offline" };
```

### Frontend (React + TypeScript)

Static build served via Nginx pod behind Cloudflare Tunnel.

**Stack:**

- React 18+ with TypeScript
- TanStack Router (file-based routing)
- TanStack Query (server state, Firestore real-time integration)
- Zustand (client state: active filters, UI mode, local preferences)
- Native WebSocket client (connection to gateway for game state + audio)
- `@ricky0123/vad-web` (Silero VAD for browser-side voice activity detection)

**Build:**

- Bazel `rules_js` / `rules_ts` for monorepo integration
- Output: static HTML/JS/CSS bundle
- Deployed as ConfigMap or baked into Nginx container image

---

## GCP Serverless Services

Summary of all GCP services used, their purpose, and pricing. **Requires Tier 1 (pay-as-you-go) for Gemini Live concurrent session limits.**

| Service                           | Purpose                                      | Pricing Model                                                              | Estimated Monthly Cost |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- | ---------------------- |
| **Firestore**                     | All game state, vectors, real-time sync      | $0.06/100K reads, $0.18/100K writes, free tier: 50K reads + 20K writes/day | ~$0.05                 |
| **Cloud Run (API)**               | Go API, scales to zero                       | Free tier: 2M requests/month, 360K vCPU-seconds                            | ~$0.00                 |
| **Cloud Run (Ingest)**            | PDF processing jobs                          | Per-job, ~$0.02 per sourcebook                                             | ~$0.03/book            |
| **Cloud Storage**                 | PDFs, extracted art                          | $0.020/GB/month, $0.004/10K operations                                     | ~$0.02                 |
| **Gemini 2.0 Flash Live**         | Voice transcription + classification + tools | $0.70/1M input tokens (audio ~25 tok/s), $0.40/1M output                   | ~$1.68                 |
| **Gemini 2.0 Flash**              | RAG answers, summaries, encounter gen        | $0.10/1M input, $0.40/1M output                                            | ~$0.25                 |
| **text-embedding-005**            | Vector embeddings (768-dim)                  | $0.15/1M tokens                                                            | ~$0.01                 |
| **Firebase Hosting** _(optional)_ | Static frontend alternative to homelab Nginx | Free tier: 10GB transfer/month                                             | $0.00                  |
|                                   |                                              | **Total**                                                                  | **~$2.01/month**       |

Assumes: 4 sessions/month, 4 hours each, 5 participants, ~30% talk time (VAD-filtered), ~50 RAG queries/session. New GCP accounts receive $300 in free credits, covering ~150 months of Grimoire usage.

---

## RAG Pipeline

```mermaid
flowchart TB
    Trigger["Trigger<br/>· Rules question detected by Gemini Live<br/>· DM types in rule lookup search<br/>· Tool call from voice classification"]
    -->Embed["Embed query<br/>text-embedding-005<br/>768-dim vector"]
    -->Search["Firestore vector search<br/>sourcebook_chunks collection<br/>cosine similarity, top-5<br/>+ metadata filters"]
    -->Assemble["Assemble context<br/>· Top-k chunks with citations<br/>· Active encounter context<br/>· Pinned chunks<br/>· Token budget: 8,192"]
    -->Generate["Gemini 2.0 Flash<br/>System: 'Answer this D&D rules question<br/>using only the provided context.<br/>Cite source book and page.'"]
    -->Response["Structured response<br/>· Answer text<br/>· Citations (book + page)<br/>· Relevance scores<br/>· Surfaced in DM context panel"]

    style Trigger fill:#fffbeb,stroke:#d97706,color:#1a1a1a
    style Response fill:#ecfdf5,stroke:#059669,color:#1a1a1a
```

### Metadata Filters

Firestore vector queries support metadata filters to scope results:

| Filter            | Use Case                        | Example                               |
| ----------------- | ------------------------------- | ------------------------------------- |
| `content_type`    | Monster lookup vs rule lookup   | `content_type == "monster"`           |
| `source_book`     | Restrict to allowed sourcebooks | `source_book in ["PHB", "MM", "DMG"]` |
| `page`            | Narrow to specific section      | `page >= 189 AND page <= 211`         |
| `metadata.cr`     | Monster challenge rating        | `metadata.cr == "3"`                  |
| `metadata.level`  | Spell/feature level             | `metadata.level <= 3`                 |
| `metadata.school` | Spell school                    | `metadata.school == "evocation"`      |

### Context Panel (DM-only)

The DM's context panel shows what the LLM is "thinking about" — the active RAG chunks plus any pinned context. Each chunk displays:

- Source citation (book + page)
- Content title
- Relevance score (percentage)
- Pin/drop controls
- "Auto" badge if surfaced by voice classification

Token budget bar shows `{used} / 8,192` tokens. DM can pin critical context to ensure it's always included, or drop irrelevant chunks.

---

## Classification System

Six categories, each with a distinct visual treatment in the DM view.

```mermaid
flowchart LR
    subgraph Input["Audio Input"]
        Voice["Player/DM speaks"]
    end

    subgraph Gemini["Gemini Live Classification"]
        Transcribe["Transcribe"]
        Classify["Classify + confidence"]
    end

    subgraph Categories["Categories"]
        IC_A["⚔ ic_action<br/><i>I attack the goblin</i>"]
        IC_D["💬 ic_dialogue<br/><i>Hail, innkeeper!</i>"]
        Rules["📖 rules_question<br/><i>Does that provoke an AoO?</i>"]
        DM_N["🎭 dm_narration<br/><i>The cave opens into...</i>"]
        DM_R["⚖ dm_ruling<br/><i>I'll allow it with disadvantage</i>"]
        Table["☕ table_talk<br/><i>Anyone want pizza?</i>"]
    end

    subgraph Effects["Downstream Effects"]
        E_State["Update encounter state"]
        E_Log["Append to narrative log"]
        E_RAG["Trigger RAG lookup"]
        E_Lore["Propagate to player lore"]
        E_Ruling["Log ruling for consistency"]
        E_Filter["Filter from player view"]
    end

    Voice --> Transcribe --> Classify
    Classify --> IC_A --> E_State
    Classify --> IC_D --> E_Log
    Classify --> Rules --> E_RAG
    Classify --> DM_N --> E_Lore
    Classify --> DM_R --> E_Ruling
    Classify --> Table --> E_Filter

    style Input fill:#f8f8f6,stroke:#1a1a1a,color:#1a1a1a
    style Gemini fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    style Categories fill:#fff,stroke:#e5e4e2,color:#1a1a1a
    style Effects fill:#f0fdf4,stroke:#16a34a,color:#1a1a1a
```

### Classification → Effect Matrix

| Classification   | Icon | Color            | DM View             | Player View    | Auto-Triggers             |
| ---------------- | ---- | ---------------- | ------------------- | -------------- | ------------------------- |
| `ic_action`      | ⚔    | Blue `#2563eb`   | Shown with pill     | Shown, no pill | Encounter state hints     |
| `ic_dialogue`    | 💬   | Purple `#7c3aed` | Shown with pill     | Shown, no pill | Narrative log             |
| `rules_question` | 📖   | Amber `#d97706`  | Shown + left border | Shown, no pill | RAG lookup, context panel |
| `dm_narration`   | 🎭   | Green `#059669`  | Shown with pill     | Shown, no pill | Lore propagation          |
| `dm_ruling`      | ⚖    | Teal `#0891b2`   | Shown with pill     | Shown, no pill | Ruling log                |
| `table_talk`     | ☕   | Grey `#9ca3af`   | Shown (filterable)  | **Hidden**     | None                      |

### Confidence & Reclassification

- Confidence ≥ 85%: classification pill only
- Confidence < 85%: amber "Low conf." warning pill in DM view
- DM can reclassify any event with one click (small icon buttons per feed item)
- Reclassification triggers re-evaluation of downstream effects (e.g., reclassifying table_talk → ic_action surfaces it in player feeds)

### Lore Propagation

When `dm_narration` or `dm_ruling` reveals new information:

1. Gemini extracts the factual content
2. Facts are tagged with which players were present (or whisper target)
3. Written to the character's lore subcollection
4. Player's "Known Lore" sidebar updates in real-time with "New" badge
5. DM can review/edit lore entries before or after propagation

---

## UI Specification

**Reference implementation**: `services/grimoire/example-ui.jsx`

### Design Language

| Token              | Value                                 |
| ------------------ | ------------------------------------- |
| Background         | `#fafaf8` (off-white)                 |
| Card background    | `#fff`                                |
| Muted background   | `#f0efed`                             |
| Foreground         | `#1a1a1a`                             |
| Muted text         | `#666`                                |
| Dim text           | `#999`                                |
| Border             | `#e5e4e2`                             |
| Accent             | `#2563eb` (blue)                      |
| OK                 | `#16a34a` (green)                     |
| Warning            | `#d97706` (amber)                     |
| Error              | `#dc2626` (red)                       |
| Private            | `#9333ea` (purple)                    |
| Prose font         | `Inter`, system-ui, sans-serif        |
| Data font          | ui-monospace, SF Mono, Cascadia Mono  |
| Base font size     | 14px                                  |
| Line height        | 1.55                                  |
| Card border radius | 4px                                   |
| Section headers    | 11px, uppercase, 1.2px letter-spacing |

**Typography rules**: Inter for all prose and UI chrome. Monospace only for: dice formulas, HP/AC values, timestamps, token counts, source citations, roll results.

### Four Views

```mermaid
flowchart TB
    subgraph App["Grimoire"]
        direction LR
        subgraph DM["DM Views"]
            DMLive["Live Session<br/>· Unified feed + filters<br/>· Initiative tracker<br/>· LLM context panel<br/>· Chat input (public/whisper/narrate)"]
            DMPrep["Session Prep<br/>· Planned encounters<br/>· Party overview<br/>· Session history<br/>· World state<br/>· Rule lookup"]
        end
        subgraph Player["Player Views"]
            PLive["Live Session<br/>· Clean narrative feed<br/>· Character summary sidebar<br/>· Quick rolls<br/>· Known lore (auto-updated)"]
            PChar["Character<br/>· Full character sheet<br/>· Inventory management<br/>· Journal (editable notes)<br/>· Known lore (read-only)"]
        end
    end

    style DM fill:#fffbeb,stroke:#d97706,color:#1a1a1a
    style Player fill:#eff4ff,stroke:#2563eb,color:#1a1a1a
```

### DM — Live Session Layout

```
┌─────────────────────────────────────────────────┬────────────────────┐
│ Voice Bar: [● Connected] Kael Lyra Theron •Vex  │ Gemini Live ~280ms │
├─────────────────────────────────────────────────┼────────────────────┤
│ Filter: [⚔ Action 3] [💬 Dialogue 2] [📖 Rules │ INITIATIVE  Rd 2   │
│   2] [🎭 Narration 5] [⚖ Ruling 1] [☕ Table 2]│                    │
├─────────────────────────────────────────────────┤ 22  Vex      15/33 │
│                                                 │ 17  Kael     45/52 │
│  DM  19:42  🎙  🎭 Narration                   │ 15  Lyra     28/28 │
│  As you push through the undergrowth, the       │ 14  Gob Boss 11/21 │
│  forest goes quiet...                           │ 12  Theron   38/41 │
│                                                 │  8  Owlbear  42/59 │
│  Vex  19:42  🎙  ⚔ Action                      │  6  Goblin×3  7/7  │
│  I stop and hold up a fist. Perception check.   │                    │
│                                                 │ [Next Turn] [End]  │
│  ┌─ 19:42  Vex  Perception  1d20+3      18 ─┐  ├────────────────────┤
│                                                 │ LLM CONTEXT  Flash │
│  Lyra  19:43  🎙  📖 Rules   ↳ RAG triggered   │ 4,102 / 8,192      │
│  ██ Can I cast Bless before combat?             │                    │
│                                                 │ PHB p.203  Auto    │
│  DM  19:43  🎙  ⚖ Ruling                       │ Concentration      │
│  Vex spotted them, party not surprised.         │ Con save DC 10 or  │
│                                                 │ half damage...     │
│  ┌─────────────────────────────────────────┐    │                    │
│  │ 🟣 Private to vex          DM   19:44  │    │ MM p.249  📌       │
│  │ He's calling reinforcements. 2 rounds.  │    │ Owlbear            │
│  └─────────────────────────────────────────┘    │ Multiattack: beak  │
│                                                 │ + claws. Keen...   │
│ ┌─────────────────────────────────────────────┐ │                    │
│ │ [Public ▾] Message the table...             │ │ [Ask a rule...]    │
│ └─────────────────────────────────────────────┘ └────────────────────┘
```

### Player — Live Session Layout

```
┌─────────────────────────────────────────────────┬────────────────────┐
│ Voice Bar: [● Connected] Kael Lyra Theron •Vex  │ Gemini Live ~280ms │
├─────────────────────────────────────────────────┼────────────────────┤
│                                                 │ VEX  Rogue 5  AC15 │
│  DM  19:42                                      │ ████████░░░  19/33 │
│  As you push through the undergrowth, the       │ ⚠ Poisoned         │
│  forest goes quiet...                           │ STR DEX CON INT WIS│
│                                                 │  +0  +4  +1  +2  +0│
│  Vex  19:42                                     ├────────────────────┤
│  I stop and hold up a fist. Perception check.   │ QUICK ROLLS        │
│                                                 │ Shortsword   1d20+7│
│  ┌─ 19:42  Vex  Perception  1d20+3      18 ─┐  │ Damage        1d6+4│
│                                                 │ Sneak Attack    3d6│
│  DM  19:42                                      │ Stealth     1d20+10│
│  You spot movement in the canopy — a massive    │ Perception   1d20+3│
│  shape on a thick branch. Below, goblins.       │ [Custom: 2d6+3   ] │
│                                                 ├────────────────────┤
│  ┌─────────────────────────────────────────┐    │ KNOWN LORE         │
│  │ 🟣 From DM — Private          19:44    │    │                    │
│  │ You understand Goblin — he's calling    │    │ 🆕 Goblin boss     │
│  │ for reinforcements. Two rounds.         │    │ called for cave    │
│  └─────────────────────────────────────────┘    │ reinforcements.    │
│                                                 │ src: Overheard S4  │
│  DM  19:45                                      │                    │
│  First swing goes wide. The second catches it.  │ Cragmaw goblins    │
│  It screams.                                    │ serve 'Black Spider│
│                                                 │ src: Goblin prisoner│
│ ┌─────────────────────────────────────────────┐ │                    │
│ │ [Public ▾] Message the table...             │ └────────────────────┘
│ └─────────────────────────────────────────────┘
```

**Key difference**: Player feed has no classification pills, no confidence scores, no reclassification buttons. Table talk is filtered out. Private messages only show those addressed to this player.

---

## Kubernetes Deployment

The homelab runs a minimal footprint: static frontend, WebSocket gateway, and Redis. Follows the existing repo conventions — service code in `services/`, Helm chart in `charts/`, ArgoCD overlay in `overlays/dev/`.

```
# Service code
services/grimoire/
├── architecture.md                      # This document
├── example-ui.jsx                       # Reference UI mockup (all 4 views)
├── frontend/                            # React app
│   ├── BUILD
│   ├── src/
│   ├── package.json
│   └── tsconfig.json
├── ws-gateway/                          # Go WS relay + Gemini Live proxy
│   ├── BUILD
│   ├── main.go
│   └── go.mod
├── api/                                 # Go Cloud Run API
│   ├── BUILD
│   ├── main.go
│   └── go.mod
└── ingest/                              # Python PDF pipeline (Cloud Run job)
    ├── BUILD
    ├── main.py
    └── requirements.txt

# Helm chart
charts/grimoire/
├── BUILD
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── frontend-deployment.yaml         # Nginx serving React build
│   ├── frontend-service.yaml
│   ├── ws-gateway-deployment.yaml       # Go WS relay + Gemini proxy
│   ├── ws-gateway-service.yaml
│   ├── redis-deployment.yaml            # Single replica, ephemeral
│   ├── redis-service.yaml
│   ├── externalsecret.yaml              # 1Password → gemini-api-key
│   └── tunnel.yaml                      # Cloudflare Tunnel CRD
└── tests/

# ArgoCD overlay
overlays/dev/grimoire/
├── BUILD
├── application.yaml                     # ArgoCD Application → charts/grimoire
├── kustomization.yaml                   # resources: [application.yaml]
└── values.yaml                          # Dev-specific Helm value overrides

# GCP bootstrap (outside K8s)
services/grimoire/gcp/
└── Makefile                             # GCP project + Cloud Run setup
```

**Conventions followed:**

- Images: `ghcr.io/jomcgi/homelab/projects/grimoire/frontend`, `ghcr.io/jomcgi/homelab/projects/grimoire/ws-gateway`
- ArgoCD Application points to `charts/grimoire` with value layering: chart defaults + `overlays/dev/grimoire/values.yaml`
- Bazel `py3_image` / `go_image` for container builds, `helm_chart` for chart packaging
- `argocd_app` BUILD rule in overlay for template rendering/testing

### Resource Requirements

| Workload          | CPU Request | Memory Request | Replicas | Node Affinity |
| ----------------- | ----------- | -------------- | -------- | ------------- |
| Frontend (Nginx)  | 50m         | 64Mi           | 1        | Any           |
| WS Gateway        | 200m        | 256Mi          | 1        | Any           |
| Redis             | 100m        | 128Mi          | 1        | Any           |
| **Total homelab** | **350m**    | **448Mi**      |          |               |

### Ingress & Authentication

All browser traffic routes through **Cloudflare Access** (SSO) before reaching the cluster. No anonymous access to any Grimoire endpoint.

**Cloudflare Access policy:**

- Application: `grimoire.yourdomain.com`
- Policy: Allow — email list (your D&D group) or identity provider (Google, GitHub, etc.)
- Session duration: 24 hours (covers a full session without re-auth)

Players authenticate once via Cloudflare's login page. The `Cf-Access-Jwt-Assertion` header is forwarded to the cluster, and the WebSocket gateway validates it to identify the player.

**Cloudflare Tunnel** via your custom operator:

```yaml
apiVersion: cloudflare.jomcgi.dev/v1alpha1
kind: Tunnel
metadata:
  name: grimoire
  namespace: grimoire
spec:
  hostname: grimoire.yourdomain.com
  service:
    name: frontend
    port: 80
  paths:
    - path: /ws
      service:
        name: ws-gateway
        port: 8080
```

All Cloud Run API calls go direct from the browser (CORS configured on Cloud Run, restricted to `grimoire.yourdomain.com` origin). The tunnel serves the frontend and WebSocket gateway. Cloud Run endpoints validate requests using the Cloudflare Access JWT or a shared origin token.

---

## GCP Bootstrap

One-time setup from your laptop using `gcloud` auth. No GCP credentials stored in the cluster.

### Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- A GCP billing account linked
- 1Password Connect Server deployed in cluster (via External Secrets Operator)

### Makefile

```makefile
PROJECT_ID    := grimoire-prod
REGION        := us-west1
FIRESTORE_DB  := grimoire
GCS_BUCKET    := grimoire-sourcebooks
API_IMAGE     := gcr.io/$(PROJECT_ID)/grimoire-api
INGEST_IMAGE  := gcr.io/$(PROJECT_ID)/grimoire-ingest

# ──────────────────────────────────────────────
# Bootstrap — run once
# ──────────────────────────────────────────────

.PHONY: setup
setup: setup-project setup-apis setup-firestore setup-storage setup-artifact-registry
	@echo ""
	@echo "✅ GCP infrastructure ready."
	@echo "Next steps:"
	@echo "  1. Create Gemini API key: https://aistudio.google.com/apikey"
	@echo "  2. Store Gemini API key in 1Password (vault: Homelab, item: grimoire-gemini-api-key)"
	@echo "  3. Deploy API: make deploy-api"
	@echo "  4. Ingest a sourcebook: make ingest PDF=gs://$(GCS_BUCKET)/phb.pdf"

setup-project:
	gcloud projects create $(PROJECT_ID) --name="Grimoire" 2>/dev/null || true
	gcloud config set project $(PROJECT_ID)
	@echo "⚠️  Link a billing account if not already done:"
	@echo "   https://console.cloud.google.com/billing/linkedaccount?project=$(PROJECT_ID)"

setup-apis:
	gcloud services enable \
		firestore.googleapis.com \
		run.googleapis.com \
		storage.googleapis.com \
		artifactregistry.googleapis.com \
		generativelanguage.googleapis.com \
		aiplatform.googleapis.com

setup-firestore:
	gcloud firestore databases create \
		--database=$(FIRESTORE_DB) \
		--location=$(REGION) \
		--type=firestore-native 2>/dev/null || true
	@echo "📦 Firestore database '$(FIRESTORE_DB)' ready in $(REGION)"
	@echo "⚠️  Create vector index manually in console or via gcloud alpha:"
	@echo "   Collection: sourcebook_chunks"
	@echo "   Field: embedding, Dimensions: 768, Distance: COSINE"

setup-storage:
	gcloud storage buckets create gs://$(GCS_BUCKET) \
		--location=$(REGION) \
		--uniform-bucket-level-access 2>/dev/null || true
	@echo "📦 Cloud Storage bucket '$(GCS_BUCKET)' ready"

setup-artifact-registry:
	gcloud artifacts repositories create grimoire \
		--repository-format=docker \
		--location=$(REGION) 2>/dev/null || true
	@echo "📦 Artifact Registry 'grimoire' ready"

# ──────────────────────────────────────────────
# Secrets — managed by 1Password + External Secrets Operator
# ──────────────────────────────────────────────
# The Gemini API key is stored in 1Password and synced to the cluster
# automatically by the External Secrets Operator. No manual secret
# creation needed — just store the key in 1Password:
#
#   Vault: Homelab
#   Item:  grimoire-gemini-api-key
#   Field: key
#
# The ExternalSecret resource (k8s/base/secrets/gemini-api-key.yaml)
# references this 1Password item and creates the K8s secret.

# ──────────────────────────────────────────────
# Deploy — push containers + update Cloud Run
# ──────────────────────────────────────────────

build-api:
	docker build -t $(API_IMAGE):latest apps/api/
	docker push $(API_IMAGE):latest

build-ingest:
	docker build -t $(INGEST_IMAGE):latest apps/ingest/
	docker push $(INGEST_IMAGE):latest

deploy-api: build-api
	gcloud run deploy grimoire-api \
		--image=$(API_IMAGE):latest \
		--region=$(REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--set-env-vars="GCP_PROJECT_ID=$(PROJECT_ID),FIRESTORE_DATABASE=$(FIRESTORE_DB),CF_ACCESS_TEAM=your-team.cloudflareaccess.com" \
		--set-secrets="GOOGLE_API_KEY=google-api-key:latest" \
		--min-instances=0 \
		--max-instances=2 \
		--memory=256Mi \
		--cpu=1 \
		--concurrency=80
	@echo "🚀 API deployed to Cloud Run"
	@echo "   Note: Cloud Run uses GOOGLE_API_KEY for Gemini Flash (RAG) + embeddings"
	@echo "   The homelab WS Gateway uses a separate secret synced from 1Password"

# ──────────────────────────────────────────────
# Ingest — process a sourcebook PDF
# ──────────────────────────────────────────────

upload-pdf:
	@test -n "$(FILE)" || (echo "Usage: make upload-pdf FILE=./phb.pdf" && exit 1)
	gcloud storage cp $(FILE) gs://$(GCS_BUCKET)/

ingest:
	@test -n "$(PDF)" || (echo "Usage: make ingest PDF=gs://$(GCS_BUCKET)/phb.pdf" && exit 1)
	gcloud run jobs execute grimoire-ingest \
		--region=$(REGION) \
		--set-env-vars="PDF_URI=$(PDF),GCP_PROJECT_ID=$(PROJECT_ID),FIRESTORE_DATABASE=$(FIRESTORE_DB)" \
		--wait

# ──────────────────────────────────────────────
# Teardown — remove everything
# ──────────────────────────────────────────────

teardown:
	@echo "⚠️  This will delete all Grimoire GCP resources. Ctrl+C to cancel."
	@sleep 5
	gcloud run services delete grimoire-api --region=$(REGION) --quiet || true
	gcloud run jobs delete grimoire-ingest --region=$(REGION) --quiet || true
	gcloud storage rm -r gs://$(GCS_BUCKET) || true
	gcloud firestore databases delete --database=$(FIRESTORE_DB) --quiet || true
	gcloud artifacts repositories delete grimoire --location=$(REGION) --quiet || true
	@echo "🗑️  GCP resources deleted. Project $(PROJECT_ID) still exists."
```

### Workflow

```
1.  gcloud auth login                    ← authenticate on your laptop
2.  make setup                           ← creates GCP project, Firestore, GCS, etc.
3.  Create Gemini API key in browser     ← https://aistudio.google.com/apikey
4.  Store Gemini API key in 1Password    ← ESO syncs it to cluster automatically
5.  git add . && git push                ← ArgoCD syncs cluster workloads
6.  make deploy-api                      ← builds + deploys Cloud Run API
7.  make upload-pdf FILE=./phb.pdf       ← upload sourcebook
8.  make ingest PDF=gs://grimoire-sourcebooks/phb.pdf  ← process it
```

After initial setup, the only commands you run regularly are `make deploy-api` when you update the Go code, and `make ingest` when you add a new sourcebook.

---

## Security Model

```mermaid
flowchart TB
    subgraph Laptop["Your Laptop"]
        GCLOUD["gcloud CLI<br/>Authenticated via<br/>Google account"]
    end

    subgraph CF_Auth["Cloudflare"]
        CFAccess2["Cloudflare Access<br/><i>SSO gate for all players</i><br/>· Email allowlist<br/>· 24h session tokens"]
    end

    subgraph GCP_IAM["GCP"]
        Project["grimoire-prod<br/>Project"]
        SA_Run["Cloud Run SA<br/><i>auto-created</i><br/>· Firestore read/write<br/>· GCS read/write<br/>· Gemini API calls"]
        SA_Ingest["Ingest Job SA<br/><i>auto-created</i><br/>· Firestore write<br/>· GCS read<br/>· Embedding API"]
    end

    subgraph Cluster["Homelab K8s"]
        Sealed["ExternalSecret<br/>gemini-api-key<br/><i>synced from 1Password</i><br/><i>consumed by WS Gateway only</i>"]
        FE2["Frontend<br/><i>no secrets</i>"]
        WS2["WS Gateway<br/><i>Gemini Live proxy</i>"]
    end

    subgraph Browsers["Player Browsers"]
        B["Authenticated session<br/><i>Cloudflare Access JWT</i><br/><i>No API keys</i>"]
    end

    GCLOUD -->|"make setup<br/>make deploy-api"| Project
    Project --> SA_Run
    Project --> SA_Ingest
    Sealed -.->|"API key at runtime"| WS2
    B -->|"Authenticated via<br/>CF Access JWT"| CFAccess2
    CFAccess2 -->|"Tunnel"| FE2
    CFAccess2 -->|"Tunnel"| WS2
    WS2 -->|"Gemini API key<br/>(server-side only)"| GCP_IAM

    style Laptop fill:#f8f8f6,stroke:#1a1a1a,color:#1a1a1a
    style CF_Auth fill:#fff3e0,stroke:#f97316,color:#1a1a1a
    style GCP_IAM fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    style Cluster fill:#f0fdf4,stroke:#16a34a,color:#1a1a1a
    style Browsers fill:#fff,stroke:#e5e4e2,color:#1a1a1a
```

### Authentication Flow

1. Player navigates to `grimoire.yourdomain.com`
2. Cloudflare Access intercepts — player authenticates via SSO (Google, GitHub, or email OTP)
3. Cloudflare issues a signed JWT (`Cf-Access-Jwt-Assertion`) valid for 24 hours
4. All subsequent requests (HTTP and WebSocket) carry this JWT
5. WS Gateway validates the JWT against Cloudflare's public keys to identify the player
6. Cloud Run API validates the JWT or a shared origin token for direct browser requests

### Credential Inventory

| Credential                 | Stored Where                                    | Access                                                                       |
| -------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------- |
| Google account (yours)     | Your laptop                                     | `gcloud auth` — provisions infrastructure, deploys Cloud Run                 |
| Cloud Run service account  | GCP-managed                                     | Auto-created, accesses Firestore/GCS. Never leaves GCP.                      |
| Gemini API key (Cloud Run) | GCP Secret Manager → Cloud Run env var          | Used by Cloud Run API for Gemini Flash (RAG) + embeddings. Never leaves GCP. |
| Gemini API key (cluster)   | 1Password → ExternalSecret → WS Gateway env var | Used by WS Gateway for Gemini Live sessions. **Never exposed to browsers.**  |
| Cloudflare Tunnel token    | Cluster secret (existing infra)                 | Routes traffic to grimoire.yourdomain.com                                    |
| Cloudflare Access JWT      | Player's browser (cookie)                       | Signed by Cloudflare, validated by WS Gateway. Identifies player.            |

### What the browsers do NOT have

- No Gemini API key
- No GCP credentials of any kind
- No direct access to Firestore or Cloud Storage
- No ability to bypass Cloudflare Access

### What the homelab cluster does NOT have

- No GCP service account keys
- No `roles/owner` credentials
- No Firestore admin access
- No ability to provision or delete GCP resources

---

## Cost Estimate

**Tier 1 (pay-as-you-go) required** for Gemini Live concurrent sessions. Enable billing on the GCP project — instant upgrade, no approval.

### Per-Session Breakdown (4 hours, 5 players + DM, VAD-filtered)

| Cost Item                  | Calculation                                                              | Cost       |
| -------------------------- | ------------------------------------------------------------------------ | ---------- |
| Voice input (audio)        | 6 participants × 30% talk time × 4 hrs × 3600 s/hr × 25 tok/s × $0.70/1M | ~$0.45     |
| Voice output (transcripts) | ~120K response tokens × $0.40/1M                                         | ~$0.05     |
| RAG queries (50/session)   | 50 × embed + vector search + Flash answer                                | ~$0.05     |
| Feed writes                | ~2,000 events × $0.18/100K                                               | ~$0.004    |
| Feed reads                 | ~10,000 reads × $0.06/100K                                               | ~$0.006    |
| **Per-session total**      |                                                                          | **~$0.50** |

### Monthly (4 sessions)

| Category                      | Cost                             |
| ----------------------------- | -------------------------------- |
| Voice (Gemini 2.0 Flash Live) | ~$2.00                           |
| Inference (Gemini Flash)      | ~$0.25                           |
| Persistence (Firestore)       | ~$0.05                           |
| Storage (Cloud Storage)       | ~$0.02                           |
| Embedding                     | ~$0.01                           |
| Cloud Run compute             | ~$0.00 (free tier)               |
| Cloudflare Access             | ~$0.00 (free for up to 50 users) |
| **Monthly total**             | **~$2.33**                       |

### VAD Impact on Cost

Browser-side Voice Activity Detection is critical for cost control:

| Scenario                          | Audio tokens/session        | Voice cost/month |
| --------------------------------- | --------------------------- | ---------------- |
| **Always-on streaming** (no VAD)  | 6 × 4hr × 25 tok/s = 2.16M  | ~$6.05           |
| **VAD-filtered** (~30% talk time) | 6 × 1.2hr × 25 tok/s = 648K | ~$2.00           |
| **Push-to-talk** (~15% active)    | 6 × 0.6hr × 25 tok/s = 324K | ~$1.00           |

VAD saves ~$4/month vs. always-on. Push-to-talk saves another ~$1 but adds friction.

### One-Time Costs

| Item                                | Cost   |
| ----------------------------------- | ------ |
| Sourcebook PDF ingestion (per book) | ~$0.03 |
| Firestore vector index creation     | Free   |

### Free Credits

New GCP accounts receive **$300 in free credits**. At ~$2.33/month, this covers **~128 months** (~10 years) of Grimoire usage before any real charges apply.

---

## Implementation Phases

### Phase 1 — Playable Foundation

Get a working session running: characters, dice, chat, basic encounter management.

**GCP:**

- [ ] `make setup` (Firestore, Cloud Storage, Cloud Run)
- [ ] Deploy grimoire-api with Campaign, Character, Dice, Feed, and Encounter services
- [ ] Store Gemini API key in 1Password (ESO syncs to cluster)
- [ ] Configure Cloudflare Access application + email allowlist

**Homelab — scaffolded in this PR:**

- [x] Helm chart (`charts/grimoire/`) — frontend, ws-gateway, redis, ExternalSecret, Tunnel
- [x] ArgoCD overlay (`overlays/dev/grimoire/`) — application.yaml, kustomization.yaml, values.yaml
- [x] Go Cloud Run API (`services/grimoire/api/`) — all CRUD routes, session/encounter state machines, Firestore handlers, CF Access JWT middleware
- [x] Go WebSocket gateway (`services/grimoire/ws-gateway/`) — connection hub, Redis pub/sub, CF Access auth, event relay, Phase 3 audio stub
- [x] React frontend (`services/grimoire/frontend/`) — all 4 views (DM Live, DM Prep, Player Live, Player Character), design system, shared components, WebSocket client, TanStack Query hooks
- [x] GCP bootstrap Makefile (`services/grimoire/gcp/`)

**Remaining for Phase 1 (future PRs):**

- [ ] Wire frontend API calls to live Cloud Run endpoint (currently uses mock data)
- [ ] End-to-end WebSocket integration (frontend ↔ gateway ↔ Firestore)
- [ ] Dice rolling with Firestore persistence and real-time broadcast
- [ ] Initiative tracker with live encounter state sync
- [ ] Chat input writing to feed subcollection via API
- [ ] Deploy to cluster and validate with ArgoCD sync
- [ ] Bazel build validation (`bazel build //services/grimoire/...`, `bazel build //charts/grimoire/...`)

**Milestone:** DM can create a campaign, add characters, run an encounter with initiative tracking, dice rolling, and chat. Players can join, see the feed, roll dice, and chat.

### Phase 2 — Intelligence Layer

Add sourcebook ingestion, RAG, and rule lookup.

- [ ] PDF ingestion pipeline (Cloud Run job)
- [ ] Firestore vector index on sourcebook_chunks
- [ ] RAG query flow: embed → search → Flash → citation
- [ ] DM context panel showing active RAG chunks with pin/drop
- [ ] Rule lookup search bar in DM Prep view
- [ ] Encounter generation from sourcebook content

**Milestone:** DM can ingest the PHB/MM/DMG, search rules with citations, and get AI-generated encounter suggestions.

### Phase 3 — Voice Pipeline

Add voice capture, server-side Gemini Live proxy, and classification.

- [ ] Browser VAD integration (`@ricky0123/vad-web` / Silero ONNX)
- [ ] WebSocket gateway Gemini Live proxy (per-player sessions, server-side API key)
- [ ] Gemini Live session reconnection handler (transparent ~10-15 min rollovers)
- [ ] Classification system with six categories
- [ ] Voice bar with speaking indicators
- [ ] Unified feed with classification pills + filter bar
- [ ] Auto-RAG triggering from rules questions
- [ ] DM reclassification controls
- [ ] Tool calls: lookup_rule, roll_dice, update_hp

**Milestone:** Players speak naturally, VAD filters silence, audio is proxied server-side to Gemini Live, transcripts appear in the feed with classifications. Rules questions auto-trigger lookups. DM can filter and reclassify. No API keys exposed to browsers.

### Phase 4 — Context & Lore

Automate knowledge tracking and session continuity.

- [ ] Lore service with per-player knowledge
- [ ] Auto-propagation from dm_narration classification
- [ ] End-of-session summary generation (Gemini Flash)
- [ ] World state auto-updates
- [ ] Player journal (editable notes per session)
- [ ] Cross-session search via embedded session content
- [ ] DM Prep view: session history, world state, party overview

**Milestone:** After each session, Grimoire auto-generates a summary, updates world state, and propagates new lore to each player's journal.

### Phase 5 — Polish

- [ ] Art extraction from sourcebook PDFs + gallery
- [ ] Scene display with extracted art in player view
- [ ] Character creation wizard with sourcebook integration
- [ ] Character PDF export
- [ ] Mobile-responsive player view
- [ ] Session recording + replay

### Future

- [ ] Image generation (Imagen / Flux API) for scene backgrounds
- [ ] Character portrait compositing
- [ ] Battle maps with fog of war
- [ ] Multi-campaign support with campaign switching
