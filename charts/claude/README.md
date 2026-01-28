# Claude

Web interface for Claude Code with WebSocket streaming and voice transcription.

## Overview

Self-hosted Claude Code environment with a web UI, persistent sessions, and optional voice input via Gemini transcription.

```mermaid
flowchart LR
    Users --> Frontend[Web Frontend]
    Frontend --> API[Claude API]
    API --> Claude[Claude Code]
    Claude --> Repo[Git Repository]
    API --> Gemini[Gemini Voice]
```

## Key Features

- **WebSocket streaming** - Real-time conversation updates
- **Voice transcription** - Gemini-powered speech-to-text
- **Persistent sessions** - Longhorn PVC for conversation history
- **Git sync** - Automatic repository cloning and fetch
- **Multi-replica HA** - Leader election for stateful operations

## Components

| Component | Description |
| --------- | ----------- |
| **API** | Bun-based server managing Claude Code sessions |
| **Frontend** | React UI with real-time updates (optional separate deployment) |
| **Repo sync** | Sidecar keeping git repository refs fresh |

## Configuration

| Value                       | Description                        | Default              |
| --------------------------- | ---------------------------------- | -------------------- |
| `replicas`                  | Number of pod replicas             | `2`                  |
| `api.port`                  | API server port                    | `3000`               |
| `gemini.model`              | Voice transcription model          | `gemini-2.0-flash`   |
| `repoSync.enabled`          | Enable git repository sync         | `false`              |
| `persistence.size`          | PVC size for sessions              | `200Gi`              |
| `leaderElection.enabled`    | Enable leader election for HA      | `true`               |
| `defaultPermissionMode`     | Claude Code permission mode        | `""`                 |

## HA Deployment

For high availability:

1. Set `replicas: 2` or higher
2. Enable `leaderElection.enabled: true`
3. Optionally enable `frontend.enabled: true` for separate frontend scaling

Sessions are sticky to pods via leader election - each active conversation routes to a consistent backend.
