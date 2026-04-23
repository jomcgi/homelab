# Trips

Photo-based GPS trip logging with elevation enrichment.

## Overview

| Component    | Description                                                                                |
| ------------ | ------------------------------------------------------------------------------------------ |
| **backend**  | FastAPI server that replays trip data from NATS JetStream and serves REST + WebSocket APIs |
| **frontend** | Timeline view with day-by-day maps and elevation profiles                                  |
| **tools**    | CLI tools for image ingestion with EXIF extraction, elevation enrichment, trip point management, KML route import, and GoPro camera control |
| **chart**    | Helm chart for Kubernetes deployment                                                       |
| **deploy**   | ArgoCD Application, kustomization, and cluster-specific values                             |
