# Ships

Real-time AIS vessel tracking with a MapLibre GL frontend.

## Overview

| Component    | Description                                                       |
| ------------ | ----------------------------------------------------------------- |
| **ingest**   | Streams AIS position reports from AISstream.io via WebSocket      |
| **backend**  | REST + WebSocket API over SQLite with moored-vessel deduplication |
| **frontend** | MapLibre GL map with live vessel positions, types, and courses    |
| **chart**    | Helm chart for Kubernetes deployment                              |
| **deploy**   | ArgoCD Application, kustomization, and cluster-specific values    |

Detailed component documentation exists in [backend/README.md](backend/README.md), [ingest/README.md](ingest/README.md), and [chart/README.md](chart/README.md).
