# Obsidian Vault Semantic Search Design

**Date:** 2026-03-28
**Status:** Approved
**Author:** jomcgi + Claude

## Problem

The Obsidian vault MCP server supports full-text search (`search_notes`), but this only matches exact substrings. We want semantic search — "find notes about Kubernetes networking" should surface notes that discuss CNI plugins, service meshes, and ingress even if they never use the exact phrase.

## Solution

Add in-process vector embeddings to the vault-mcp server using fastembed (CPU-only, no GPU) and a colocated Qdrant instance. A background reconciliation loop keeps the index in sync with vault contents.

## Architecture

```
                    Obsidian Sync (cloud)
                           |
                   ob sync --continuous
                           |
                    vault files on disk (PVC)
                      /       |        \
             git sidecar   vault-mcp   fastembed model cache
                 |            |    \          (on PVC)
          private GitHub    MCP tools  background reconcile loop
                           /      \            |
                   CRUD tools   search_semantic
                                       |
                                    Qdrant 1.17.1
                              (subchart, same namespace)
```

### What Changes

1. **vault-mcp container** gains:
   - `fastembed` + `httpx` as new Python deps
   - A background asyncio task that reconciles every 5 minutes
   - A new `search_semantic` MCP tool
   - Memory limit bumped from 128Mi to 768Mi

2. **fastembed model** (`nomic-ai/nomic-embed-text-v1.5`, 768-dim, ~274MB):
   - Downloaded on first startup, cached at `/vault/.cache/fastembed/`
   - Stays loaded in memory for query embedding via `search_semantic`
   - Runs entirely on CPU, no GPU required

3. **Qdrant 1.17.1** added as a Helm subchart:
   - Single replica, 2Gi persistence
   - Collection `obsidian_vault` with cosine distance, 768-dim vectors
   - Service at `obsidian-vault-qdrant.obsidian.svc.cluster.local:6333`

4. **No new containers, pods, or CronJobs.**

### Cleanup

Delete `projects/blog_knowledge_graph/` entirely — the knowledge graph pipeline is being retired. Blog content will eventually flow into Obsidian notes directly, keeping a single source of truth.

## Reconciliation Loop

The background task runs on startup + every 5 minutes. Fully stateless — no marker files, no git diff parsing.

### Algorithm

1. **Walk vault:** collect `{relative_path: sha256(content)}` for all `.md` files
   - Include `_archive/`
   - Exclude `.obsidian/`, `.git/`, dotfile directories

2. **Query Qdrant:** scroll all points in `obsidian_vault` collection, group by `source_url` to get `{source_url: content_hash}`

3. **Diff:**
   - `TO_EMBED`: files where hash differs or `source_url` not in Qdrant
   - `TO_DELETE`: `source_url`s in Qdrant where file no longer exists on disk

4. **Delete stale vectors:** for each `TO_DELETE` + changed files in `TO_EMBED`, delete by `source_url` filter

5. **Embed new/changed:** `chunk_markdown(content)` → `fastembed.embed(chunks)` → `qdrant.upsert(points)`

6. **Log summary:** `"Reconciled: 3 embedded, 1 deleted, 247 unchanged"`

### Why Stateless Reconcile Over Git Diff

Git diff sounds simpler but requires: a persistent commit marker, diff status flag parsing (`M`/`D`/`R`), rebase/force-push edge cases, and a full-reconcile fallback for when the marker is lost. The stateless approach is O(n) in a cheap read (SHA256 hashing 5000 small files < 1 second), and only does expensive work (embedding) on the delta. It always converges to the correct state.

### Edge Cases

- **First run:** Qdrant empty, all files embedded. ~5-10 min for a 2000-note vault on CPU.
- **Empty vault:** no-op.
- **Qdrant unreachable:** log error, retry next cycle. CRUD tools unaffected.
- **File renamed:** old path deleted from Qdrant, new path embedded. No special handling needed.
- **File edited:** old hash chunks deleted, new hash chunks inserted.

## Qdrant Vector Payload

```json
{
    "source_url": "vault://projects/homelab.md",
    "content_hash": "abc123...",
    "title": "projects/homelab.md",
    "section_header": "## Architecture",
    "chunk_index": 2,
    "chunk_text": "The actual chunk content..."
}
```

Deterministic point IDs via `UUID5(content_hash + chunk_index)` for idempotent upserts.

## MCP Tool

```python
@mcp.tool
async def search_semantic(query: str, limit: int = 5) -> dict:
    """Semantic search across vault notes using vector embeddings.

    Args:
        query: Natural language search query.
        limit: Max results to return (default 5).

    Returns matching chunks with scores, paths, and section headers.
    """
```

Returns:
```json
{
    "results": [
        {
            "score": 0.87,
            "path": "projects/homelab.md",
            "section_header": "## Architecture",
            "chunk_text": "The cluster runs..."
        }
    ]
}
```

## Code Structure

New files in `vault_mcp/app/`:

| File | Purpose |
|------|---------|
| `embedder.py` | `VaultEmbedder` — fastembed wrapper, `embed()` + `embed_query()` |
| `reconciler.py` | `VaultReconciler` — stateless reconcile loop logic |
| `qdrant_client.py` | `QdrantClient` — ensure_collection, upsert, search, delete_by_source_url, get_indexed_sources |
| `chunker.py` | Markdown-aware chunking (ported from blog_knowledge_graph) |

### Settings

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAULT_")

    path: str = "/vault"
    port: int = 8000

    # Embedding (always on)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "obsidian_vault"
    embed_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embed_cache_dir: str = "/vault/.cache/fastembed"
    reconcile_interval_seconds: int = 300
```

Embedding is mandatory — no feature flag. The reconciler starts on server boot.

## Helm Chart Changes

### Qdrant Subchart

```yaml
# Chart.yaml
dependencies:
  - name: qdrant
    version: "1.17.1"
    repository: "https://qdrant.github.io/qdrant-helm"
```

```yaml
# values.yaml
qdrant:
  replicaCount: 1
  persistence:
    size: 2Gi
  resources:
    requests:
      memory: "256Mi"
      cpu: "100m"
    limits:
      memory: "512Mi"
```

### vault-mcp Container Updates

- `VAULT_QDRANT_URL` env var pointing at subchart service
- Memory limit: 128Mi → 768Mi
- Memory request: 64Mi → 512Mi

## Chunking Strategy

Ported from `blog_knowledge_graph/knowledge_graph/app/chunker.py`:

1. Split on markdown headers (h1-h3)
2. Within sections, split on paragraph boundaries to stay under 512 tokens
3. Code blocks kept intact even if they exceed limits
4. Small chunks (< 50 tokens) merged with previous chunk
5. Token estimate: ~1.3 tokens per word

Simplifications from KG version: drop `author`, `published_at`, `source_type` fields (not relevant for vault notes). `title` derived from file path. `source_url` is `vault://<relative_path>`.

## Resource Summary

| Component | CPU Request | Memory Request | Memory Limit |
|-----------|-------------|----------------|--------------|
| headless-sync | 50m | 128Mi | 256Mi |
| git-sidecar | 10m | 32Mi | 64Mi |
| vault-mcp | 100m | 512Mi | 768Mi |
| qdrant | 100m | 256Mi | 512Mi |
| **Total** | **260m** | **928Mi** | **1.6Gi** |

## Security

- All data stays in-cluster (no external API calls for embedding)
- Qdrant only accessible within the namespace (ClusterIP service)
- fastembed model downloaded from HuggingFace on first boot only, cached on PVC
- No new ingress or external exposure
