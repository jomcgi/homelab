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
- **Storage**: Persistent storage (1Gi) for SQLite databases
- **Resources**: 256Mi-512Mi memory, 100m-500m CPU

### Initial Setup

1. Deploy the application:
```bash
cd /workspaces/homelab/cluster/services/find-good-hikes
skaffold dev
# or
kubectl apply -k .
```

2. **First-time data setup** (only needed once or when you want fresh walking routes):
```bash
# Create a one-time job to scrape walking routes and weather data
kubectl create job --from=cronjob/find-good-hikes-scrape-once find-good-hikes-initial-scrape -n find-good-hikes

# Monitor the job
kubectl logs -f job/find-good-hikes-initial-scrape -n find-good-hikes
```

### Weather Updates

Weather forecasts are automatically updated:
- **Every 4 hours** via CronJob `find-good-hikes-weather-update`
- **At startup** if weather data is older than 6 hours (handled by entrypoint script)

### Manual Operations

Force weather update:
```bash
kubectl create job --from=cronjob/find-good-hikes-weather-update weather-update-now -n find-good-hikes
```

Re-scrape walking routes (rarely needed):
```bash
kubectl create job --from=cronjob/find-good-hikes-scrape-once fresh-routes -n find-good-hikes
```

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