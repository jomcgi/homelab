# Trips

Photo-based GPS trip logging with elevation enrichment.

## Overview

| Component    | Description                                                                                |
| ------------ | ------------------------------------------------------------------------------------------ |
| **backend**  | FastAPI server that replays trip data from NATS JetStream and serves REST + WebSocket APIs |
| **frontend** | Timeline view with day-by-day maps and per-day elevation stats (ascent, descent, min/max)  |
| **tools**    | CLI tools for image ingestion with EXIF extraction, elevation enrichment, trip point management, KML route import, and wildlife detection with GoPro camera control (`detect-wildlife`) |
| **chart**    | Helm chart for Kubernetes deployment                                                       |
| **deploy**   | ArgoCD Application, kustomization, and cluster-specific values                             |
