# Find Good Hikes Service

A web application for finding hiking routes with good weather conditions.

## Features

- Web interface for searching hiking routes
- Weather-based route recommendations
- Integration with walking route data
- Automated weather forecast updates

## Deployment

This service is deployed to the homelab Kubernetes cluster with:

- **Namespace**: `find-good-hikes`
- **Ingress**: `hikes.jomcgi.dev` (via Cloudflare Tunnel)
- **Security**: Non-root container, read-only filesystem where possible
- **Storage**: Ephemeral storage for SQLite databases
- **Resources**: 256Mi-512Mi memory, 100m-500m CPU

## Development

Use Skaffold for local development:

```bash
cd /workspaces/homelab/cluster/services/find-good-hikes
skaffold dev
```

## Security Features

- Runs as non-root user (uid 1000)
- Security context with dropped capabilities
- Read-only root filesystem (where compatible with SQLite)
- Resource limits to prevent resource exhaustion
- Health checks for liveness and readiness probes

## Architecture

The application consists of:

1. **FastAPI web server** - Handles HTTP requests
2. **SQLite databases** - Stores walking routes and weather data
3. **Scheduled tasks** - Updates weather forecasts hourly
4. **Static files** - CSS and template assets