# Obsidian Vault Integration Design

**Date:** 2026-03-21
**Status:** Draft
**Author:** jomcgi + Claude

## Problem

We want a private markdown knowledge base (Obsidian vault) that:

- Syncs across all devices via the existing paid Obsidian Sync subscription
- Is accessible to Claude (web via MCP, Code via filesystem)
- Has a full audit trail of all changes (git history)
- Can later be extended with vector search / knowledge graph capabilities

## MVP Scope

Three components, no embeddings/Qdrant in v1:

1. **Obsidian Headless** — `ob sync --continuous` in a container, keeps vault files on disk
2. **Git sidecar** — auto-commits all changes, pushes to a private GitHub repo
3. **Vault MCP server** — FastMCP Python server for reading/writing vault notes

## Non-Goals (v1)

- Embeddings / vector search (future: extend blog_knowledge_graph pipeline)
- Knowledge graph extraction
- Obsidian plugin execution (headless CLI doesn't support plugins)
- Public access to any vault content

## Architecture

```
                     Obsidian Sync (cloud)
                            |
                    ob sync --continuous
                            |
                     vault files on disk (PVC)
                       /          \
              git sidecar        vault-mcp (FastMCP)
                  |                    |
           private GitHub repo    Context Forge
                                       |
                                Claude web + Code
```

### Component 1: Obsidian Headless Container

**Image:** `node:22-alpine` base (or apko equivalent with Node.js 22)
**Command:** `ob sync --continuous`
**Auth:** Obsidian account token stored as 1Password secret (`OnePasswordItem`)
**Sync mode:** `bidirectional` — changes from MCP server sync back to all devices
**Volume:** Shared PVC mounted at `/vault`

Startup sequence:

1. `ob login` using stored credentials
2. `ob sync-setup` to configure vault
3. `ob sync --continuous` to watch for changes

### Component 2: Git Sidecar

A lightweight process (shell script or small Go binary) that:

1. Initializes `/vault` as a git repo on first run (`git init`, set remote to private GitHub repo)
2. Watches for filesystem changes (inotifywait/fsnotify or poll loop)
3. **External sync changes:** debounce 10s, then `git add -A && git commit -m "sync: external changes"` && `git push`
4. **Does NOT commit MCP changes** — the MCP server handles its own commits

**Git remote:** Private GitHub repo (e.g. `jomcgi/obsidian-vault`, private)
**Auth:** GitHub deploy key or PAT stored as 1Password secret
**Conflict handling:** The sidecar is append-only to git — no force pushes, no rebases. If push fails (diverged), it pulls with rebase first.

Race condition prevention:

- MCP server acquires a file lock before write + commit
- Git sidecar checks the same lock before committing
- Simple lockfile at `/vault/.git/mcp.lock`

### Component 3: Vault MCP Server (FastMCP)

Follows the established pattern from `todo_mcp` and `orchestrator/mcp`:

```python
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAULT_")
    vault_path: str = "/vault"
    port: int = 8000

mcp = FastMCP("ObsidianVault")
```

**Tools:**

| Tool           | Description                                                               |
| -------------- | ------------------------------------------------------------------------- |
| `list_notes`   | List markdown files, filter by folder/glob pattern                        |
| `read_note`    | Read a note's full content                                                |
| `write_note`   | Create or overwrite a note (commits with reason)                          |
| `edit_note`    | Replace a section of a note (commits with reason)                         |
| `delete_note`  | Move note to `_archive/` folder instead of deleting (commits with reason) |
| `search_notes` | Full-text search (ripgrep or Python fallback)                             |
| `get_history`  | Git log for a specific file or the whole vault                            |
| `restore_note` | Restore a file from a specific git commit                                 |

Every mutation tool:

1. Acquires lock
2. Performs file operation
3. `git add <file>` + `git commit -m "mcp(<tool>): <path> — <reason>"`
4. Releases lock

The `reason` parameter is required on all write/edit/delete operations — this becomes the commit message context.

**Soft delete:** `delete_note` moves files to `_archive/<original-path>` rather than removing them. This provides an extra safety net beyond git history.

**Registration:** Auto-registers with Context Forge gateway on startup (same pattern as existing MCP servers).

## Deployment

Deployed as a single Helm release in the `obsidian` namespace:

```
projects/
  obsidian_vault/
    chart/              # Helm chart
    deploy/
      application.yaml  # ArgoCD Application
      kustomization.yaml
      values.yaml
      imageupdater.yaml # Auto image updates for MCP server
```

**Pod structure:** Single pod with three containers sharing a PVC:

| Container       | Image                                  | Role                                      |
| --------------- | -------------------------------------- | ----------------------------------------- |
| `headless-sync` | `node:22-alpine` + `obsidian-headless` | Runs `ob sync --continuous`               |
| `git-sidecar`   | Alpine + git                           | Watches for changes, auto-commits, pushes |
| `vault-mcp`     | Custom apko image (Python + FastMCP)   | MCP server on port 8000                   |

**PVC:** `vault-data`, 5Gi, ReadWriteMany (or single pod so RWO is fine)

**Secrets (1Password):**

- `obsidian-credentials` — Obsidian account token for headless sync
- `github-deploy-key` — SSH key for pushing to private repo

## Git Commit Flow

Two distinct commit sources, distinguished by message prefix:

```
# MCP server commits (structured, with reason)
a1b2c3d mcp(write_note): daily/2026-03-21.md — "standup notes"
d4e5f6g mcp(edit_note): projects/homelab.md — "added obsidian section"
h7i8j9k mcp(delete_note): scratch/old-idea.md — "no longer relevant"

# Git sidecar commits (auto, from Obsidian Sync)
m1n2o3p sync: external changes (3 files modified)
q4r5s6t sync: external changes (1 file added)
```

## Security

- Vault PVC is not exposed outside the pod
- MCP server only accessible via Context Forge (cluster-internal)
- GitHub repo is private, accessed via deploy key (write-only, no admin)
- Obsidian credentials stored in 1Password, injected as K8s secrets
- No public ingress, no internet exposure
- `delete_note` soft-deletes to `_archive/` — never removes files

## Future Extensions (post-MVP)

- **Vector search:** CronJob watches git for new commits, chunks changed markdown, embeds via Ollama, upserts to Qdrant. Expose `search_semantic` tool on MCP server.
- **Knowledge graph:** Extract entities/relationships from notes, store in graph DB or Qdrant metadata
- **Templating:** MCP tool to create notes from templates (daily notes, meeting notes, etc.)
- **Backlinks:** MCP tool to find all notes linking to a given note (wiki-link parsing)
