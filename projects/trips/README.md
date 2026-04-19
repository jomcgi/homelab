# Trips

Photo-based GPS trip logging with elevation enrichment.

## Overview

| Component    | Description                                                                                |
| ------------ | ------------------------------------------------------------------------------------------ |
| **backend**  | Extracts GPS coordinates from photo EXIF data, enriches with elevation from NRCan CDEM API |
| **frontend** | Timeline view with day-by-day maps and elevation profiles                                  |
| **tools**    | Utilities for data processing and import                                                   |
| **chart**    | Helm chart for Kubernetes deployment                                                       |
