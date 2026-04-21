# Trips

Photo-based GPS trip logging with elevation enrichment.

## Overview

| Component    | Description                                                                                |
| ------------ | ------------------------------------------------------------------------------------------ |
| **backend**  | FastAPI server that replays trip data from NATS JetStream and serves REST + WebSocket APIs |
| **frontend** | Timeline view with day-by-day maps and elevation profiles                                  |
| **tools**    | CLI tools for EXIF extraction, elevation enrichment, trip management, and data import      |
| **chart**    | Helm chart for Kubernetes deployment                                                       |
| **deploy**   | ArgoCD Application, kustomization, and cluster-specific values                             |
