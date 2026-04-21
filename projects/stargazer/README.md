# Stargazer

Finds the best stargazing spots in Scotland for the next 72 hours.

## Overview

Multi-phase pipeline: light pollution atlas + OSM road data to identify dark zones near roads, scored by weather forecast. The backend runs as a scheduled CronJob with a separate API server for serving results.

| Component             | Description                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------ |
| **backend**           | Pipeline that combines light pollution data, OSM roads, and weather forecasts              |
| **tests**             | Test suite covering acquisition, preprocessing, spatial analysis, weather scoring, and API |
| **chart**             | Helm chart with CronJob and API server templates                                           |
| **deploy**            | ArgoCD Application, kustomization, and cluster-specific values                             |
| **implementation.md** | Detailed design document with task specs and progress log                                  |
