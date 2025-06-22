# Find Good Hikes - Deployment Guide

## 🚀 Quick Start

The find-good-hikes service is now fully containerized and ready for Kubernetes deployment with automated CI/CD.

### Automatic Deployment

The service deploys automatically via GitHub Actions when:
- Code changes are pushed to main branch
- On the 1st and 15th of each month (scheduled)
- Manually triggered via GitHub Actions

### Manual Deployment

```bash
cd /workspaces/homelab/cluster/services/find-good-hikes
skaffold dev
```

## 📁 Architecture

```
find-good-hikes/
├── namespace.yaml           # Isolated namespace
├── pvc.yaml                # 1GB persistent storage for databases
├── deployment.yaml         # Main web app with init container
├── service.yaml            # ClusterIP service
├── ingress.yaml            # Ingress for hikes.jomcgi.dev
├── cronjob.yaml            # Scheduled jobs for data updates
├── skaffold.yaml           # Development deployment
└── README.md               # Documentation
```

## 🔄 Data Management

### Initial Setup (Automatic)
The GitHub Actions workflow automatically:
1. Deploys the application
2. Checks for existing walking routes database
3. If not found, runs initial data scrape job
4. Updates weather forecasts
5. Performs health checks

### Automated Updates
- **Weather data**: Updated every 4 hours via CronJob
- **Walking routes**: Updated manually (rarely needed)
- **At startup**: Weather updates if data > 6 hours old

## 🛡️ Security Features

✅ **Container Security**
- Non-root user (uid:1000)
- Read-only root filesystem (where possible)
- Dropped capabilities
- seccomp profiles
- Resource limits

✅ **Network Security**
- No direct internet exposure
- Ingress via Cloudflare Tunnel only
- Internal ClusterIP service

✅ **Data Security**
- Persistent storage for databases
- Automated backups via Longhorn
- No sensitive data in containers

## 🌐 Access

- **Production**: https://hikes.jomcgi.dev
- **Health Check**: https://hikes.jomcgi.dev/health
- **Internal**: http://find-good-hikes.find-good-hikes.svc.cluster.local:80

## 📊 Monitoring

The service includes:
- **Health checks**: `/health` endpoint
- **Kubernetes probes**: Liveness and readiness
- **Resource monitoring**: CPU/Memory limits
- **Job monitoring**: CronJob success/failure tracking

## 🔧 Troubleshooting

### No hiking data shown
```bash
# Check if walks database exists
kubectl exec -n find-good-hikes deployment/find-good-hikes -- ls -la /app/data/

# Trigger manual data scrape
kubectl create job --from=cronjob/find-good-hikes-scrape-once manual-scrape -n find-good-hikes
kubectl logs -f job/manual-scrape -n find-good-hikes
```

### Stale weather data
```bash
# Trigger manual weather update
kubectl create job --from=cronjob/find-good-hikes-weather-update manual-weather -n find-good-hikes
kubectl logs -f job/manual-weather -n find-good-hikes
```

### Check service health
```bash
# Pod status
kubectl get pods -n find-good-hikes

# Service logs
kubectl logs -n find-good-hikes deployment/find-good-hikes --tail=50

# Port forward for local testing
kubectl port-forward -n find-good-hikes svc/find-good-hikes 8080:80
curl http://localhost:8080/health
```

## 🔄 CI/CD Pipeline

The GitHub Actions workflow (`deploy-find-good-hikes.yaml`) performs:

1. **Deploy**: Use Skaffold to build and deploy
2. **Health Check**: Verify deployment is healthy
3. **Data Setup**: Run initial scrape if needed
4. **Weather Update**: Ensure fresh forecasts
5. **Validation**: Port-forward health check
6. **Cleanup**: Remove old jobs

## 📝 Manual Operations

```bash
# Force complete data refresh (walking routes + weather)
kubectl create job --from=cronjob/find-good-hikes-scrape-once complete-refresh -n find-good-hikes

# Update only weather (common operation)
kubectl create job --from=cronjob/find-good-hikes-weather-update weather-only -n find-good-hikes

# View CronJob status
kubectl get cronjobs -n find-good-hikes

# View job history
kubectl get jobs -n find-good-hikes

# Scale deployment
kubectl scale deployment find-good-hikes --replicas=2 -n find-good-hikes
```

## 🎯 Performance

- **Startup time**: ~30 seconds
- **Memory usage**: 256-512 MB
- **CPU usage**: 100-500m
- **Storage**: <1GB for databases
- **Response time**: <2s for search queries

The service is designed for efficiency with:
- SQLite local databases (fast queries)
- Cached weather API requests
- Minimal resource footprint
- Persistent storage (no data loss on restarts)