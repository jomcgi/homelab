# Obsidian Vault Helm Chart

A Kubernetes Helm chart that deploys an [Obsidian](https://obsidian.md) vault with semantic search, git-based version history, and an [MCP](https://modelcontextprotocol.io/) server for AI agent access.

## What Gets Deployed

The chart runs up to three containers in a single pod, backed by a shared PersistentVolumeClaim:

| Container         | Purpose                                                     | Always On?                  |
| ----------------- | ----------------------------------------------------------- | --------------------------- |
| **vault-mcp**     | MCP server exposing vault read/write/search tools over HTTP | Yes                         |
| **git-sidecar**   | Watches for file changes and commits them to a GitHub repo  | Yes                         |
| **headless-sync** | Syncs with Obsidian's cloud service                         | No (`headlessSync.enabled`) |

A [Qdrant](https://qdrant.tech/) vector database is deployed as a subchart, powering semantic search over your notes via local CPU-based embeddings.

### MCP Tools

The MCP server exposes these tools for AI agents:

- `list_notes` / `read_note` / `search_notes` — browse and full-text search
- `search_semantic` — vector similarity search over note embeddings
- `write_note` / `edit_note` / `delete_note` — modify notes (each operation creates a git commit)
- `get_history` / `restore_note` — view and restore from git history

All write operations require a `reason` parameter which becomes part of the git commit message.

## Prerequisites

- Kubernetes 1.24+
- Helm 3
- [1Password Operator](https://developer.1password.com/docs/k8s/k8s-operator/) (for secrets management)
- A GitHub repository for the git audit trail
- A GitHub token with push access to that repository

## Installation

```bash
helm repo add oci://ghcr.io/jomcgi/homelab/charts
helm install obsidian-vault oci://ghcr.io/jomcgi/homelab/charts/obsidian-vault \
  --version 0.5.16 \
  --namespace obsidian --create-namespace \
  -f my-values.yaml
```

## Configuration

### Minimal `values.yaml`

```yaml
gitSidecar:
  remote: "https://github.com/<you>/<your-vault-repo>.git"

secrets:
  obsidian:
    itemPath: "vaults/<your-1password-vault>/items/<item-name>"
```

The 1Password item should contain a `token` field with your GitHub personal access token.

### Enabling Obsidian Cloud Sync

If you use Obsidian Sync, enable the headless sync container to keep the vault up to date with your cloud vault:

```yaml
headlessSync:
  enabled: true
  vaultName: "<your-obsidian-vault-name>"
```

The 1Password item for `secrets.obsidian` should additionally contain `email` and `password` fields matching your Obsidian account.

### MCP Gateway Registration

To register the MCP server with a [Context Forge](https://github.com/IBM/mcp-context-forge) gateway (so AI agents can discover it), configure:

```yaml
gateway:
  url: "http://<gateway-service>.<namespace>.svc.cluster.local:80"
  secret:
    itemPath: "vaults/<your-1password-vault>/items/<gateway-secret>"
```

A Helm post-install hook will automatically register the server with the gateway.

### Full Values Reference

| Key                                  | Default                          | Description                                           |
| ------------------------------------ | -------------------------------- | ----------------------------------------------------- |
| `headlessSync.enabled`               | `false`                          | Enable Obsidian cloud sync sidecar                    |
| `headlessSync.vaultName`             | `""`                             | Obsidian vault name to sync                           |
| `headlessSync.image`                 | `node:22-alpine`                 | Headless sync container image                         |
| `gitSidecar.image`                   | `alpine/git:latest`              | Git sidecar container image                           |
| `gitSidecar.remote`                  | `""`                             | GitHub repo URL for audit trail                       |
| `gitSidecar.branch`                  | `main`                           | Git branch to push to                                 |
| `gitSidecar.debounceSeconds`         | `10`                             | Seconds to wait before committing changes             |
| `vaultMcp.port`                      | `8000`                           | MCP server listen port                                |
| `persistence.size`                   | `5Gi`                            | PVC size for vault storage                            |
| `persistence.storageClass`           | `""`                             | Storage class (empty = cluster default)               |
| `embedding.qdrantCollection`         | `obsidian_vault`                 | Qdrant collection name                                |
| `embedding.model`                    | `nomic-ai/nomic-embed-text-v1.5` | Embedding model                                       |
| `embedding.reconcileIntervalSeconds` | `300`                            | How often to re-index changed notes                   |
| `qdrant.replicaCount`                | `1`                              | Qdrant replicas                                       |
| `qdrant.persistence.size`            | `2Gi`                            | Qdrant storage size                                   |
| `gateway.url`                        | `""`                             | Context Forge gateway URL (empty = skip registration) |
| `secrets.obsidian.itemPath`          | `""`                             | 1Password item path for Obsidian/GitHub credentials   |

### Resource Defaults

| Container     | Memory Request | Memory Limit | CPU Request |
| ------------- | -------------- | ------------ | ----------- |
| headless-sync | 128Mi          | 384Mi        | 50m         |
| git-sidecar   | 128Mi          | 1Gi          | 10m         |
| vault-mcp     | 8Gi            | 16Gi         | 100m        |
| qdrant        | 256Mi          | 512Mi        | 100m        |

The vault-mcp container needs significant memory because it loads the embedding model (~1.5GB) into memory for local inference.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Pod: obsidian-vault                                │
│                                                     │
│  ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ headless-sync│  │ git-sidecar│  │  vault-mcp │  │
│  │  (optional)  │  │            │  │  (FastMCP)  │  │
│  │              │  │ watch ──┐  │  │   :8000     │  │
│  │ obsidian     │  │ commit  │  │  │             │  │
│  │ cloud sync   │  │ push    │  │  │  embedding  │  │
│  └──────┬───────┘  └────┬────┘  │  │  + search   │  │
│         │               │       │  └──────┬──────┘  │
│         ▼               ▼       │         │         │
│  ┌──────────────────────────────┘         │         │
│  │        /vault (PVC, 5Gi)               │         │
│  └────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   ┌─────────────┐               ┌─────────────┐
   │   GitHub    │               │   Qdrant    │
   │   (audit)   │               │  (vectors)  │
   └─────────────┘               └─────────────┘
```

## Notes

- **Storage is RWO** — the deployment strategy is `Recreate`, not `RollingUpdate`, since the PVC can only be mounted by one pod at a time.
- **Soft deletes** — `delete_note` moves files to `_archive/` rather than permanently removing them.
- **Embedding runs on CPU** — no GPU required. The `nomic-embed-text-v1.5` model runs via [FastEmbed](https://github.com/qdrant/fastembed) with single-threaded inference.
- **Reconciliation** — a background loop re-indexes changed notes every 5 minutes (configurable). It uses SHA256 content hashing to detect changes efficiently.
