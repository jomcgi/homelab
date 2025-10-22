# FreshRSS Helm Chart

A security-first Helm chart for deploying [FreshRSS](https://freshrss.org/), a self-hosted RSS feed aggregator, to Kubernetes.

## Features

- **Security-hardened** deployment with non-root containers and read-only filesystems where possible
- **Persistent storage** using Longhorn for data and extensions
- **Automatic feed refresh** via built-in cron job
- **Health checks** for liveness and readiness probes
- **Resource limits** to prevent resource exhaustion
- **Cloudflare Tunnel ready** - designed to run behind zero-trust ingress
- **No authentication required** - secured externally via Cloudflare Access

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- Longhorn storage class (or modify `persistence.data.storageClass` and `persistence.extensions.storageClass`)

## Installation

### Basic Installation

```bash
# Install with default values (SQLite database, 5Gi data volume)
helm install freshrss ./charts/freshrss -n freshrss --create-namespace
```

### Custom Installation

```bash
# Create a values file
cat > my-values.yaml <<EOF
freshrss:
  timezone: "America/New_York"
  cronMinutes: "5,35"  # Refresh feeds at 5 and 35 minutes past each hour

persistence:
  data:
    size: 10Gi
  extensions:
    size: 2Gi

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 200m
    memory: 256Mi
EOF

# Install with custom values
helm install freshrss ./charts/freshrss -n freshrss --create-namespace -f my-values.yaml
```

### With Auto-Install and User Creation

```bash
cat > auto-install-values.yaml <<EOF
freshrss:
  timezone: "UTC"
  cronMinutes: "1,31"
  install:
    enabled: true
    apiEnabled: true
    baseUrl: "https://freshrss.example.net"
    dbType: "sqlite"
    defaultUser: "admin"
    language: "en"
  user:
    enabled: true
    username: "admin"
    password: "changeme"  # Use 1Password secrets in production
    email: "admin@example.net"
    apiPassword: "api-changeme"  # Use 1Password secrets in production
    language: "en"
EOF

helm install freshrss ./charts/freshrss -n freshrss --create-namespace -f auto-install-values.yaml
```

## Configuration

### Key Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | FreshRSS Docker image repository | `freshrss/freshrss` |
| `image.tag` | Image tag | `latest` |
| `freshrss.timezone` | Server timezone | `UTC` |
| `freshrss.cronMinutes` | Cron schedule for feed refresh | `1,31` |
| `freshrss.environment` | Environment mode (production/development) | `production` |
| `persistence.data.enabled` | Enable persistent data storage | `true` |
| `persistence.data.size` | Data volume size | `5Gi` |
| `persistence.data.storageClass` | Storage class for data | `longhorn` |
| `persistence.extensions.enabled` | Enable persistent extensions storage | `true` |
| `persistence.extensions.size` | Extensions volume size | `1Gi` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |

### Security Configuration

The chart includes security hardening while allowing necessary initialization:

```yaml
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false
  capabilities:
    drop:
      - ALL

podSecurityContext:
  fsGroup: 33
  seccompProfile:
    type: RuntimeDefault
```

**Security Trade-offs:**
- Container runs as root for initialization (timezone, PHP/Apache config, cron setup)
- Apache web server runs as www-data internally for security
- Read-only root filesystem is disabled (FreshRSS needs to write configs)
- All capabilities are dropped to minimize attack surface
- This follows the official FreshRSS Docker image design

## Architecture Integration

### Cloudflare Tunnel Integration

This chart is designed to work with Cloudflare Tunnel for secure ingress:

1. Deploy FreshRSS with this chart
2. Configure Cloudflare Tunnel to point to the FreshRSS service:
   ```yaml
   # In your Cloudflare Tunnel config
   ingress:
     - hostname: freshrss.example.net
       service: http://freshrss.freshrss.svc.cluster.local:80
   ```
3. Configure Cloudflare Access policies for authentication

### Storage

The chart uses two persistent volumes:
- **Data volume**: Stores FreshRSS configuration and SQLite database
- **Extensions volume**: Stores third-party extensions

Both use Longhorn storage class by default for high availability.

### Observability

The deployment includes:
- **Liveness probes**: Ensure the container is running
- **Readiness probes**: Ensure the service is ready to accept traffic
- **Resource limits**: Prevent runaway resource consumption

## Usage

### Accessing FreshRSS

```bash
# Port-forward for local access
kubectl port-forward -n freshrss svc/freshrss 8080:80

# Visit http://localhost:8080
```

### CLI Commands

```bash
# List users
kubectl exec -n freshrss deployment/freshrss --user www-data -- cli/list-users.php

# Create a user
kubectl exec -n freshrss deployment/freshrss --user www-data -- cli/create-user.php \
  --user myuser --password mypassword

# Refresh feeds manually
kubectl exec -n freshrss deployment/freshrss --user www-data -- cli/actualize-script.php
```

### Backup and Migration

**Important**: PVCs persist through pod restarts but are **deleted** if the PVC itself is deleted. Always maintain backups!

```bash
# Export feeds (OPML)
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-opml-for-user.php --user admin > feeds-backup.opml

# Full backup (feeds + articles + settings)
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-zip-for-user.php --user admin > freshrss-full-backup.zip

# Import OPML (via web UI)
# Settings → Subscription Management → Import → feeds-backup.opml
```

**For complete backup and disaster recovery procedures**, see [BACKUP.md](./BACKUP.md).

### Upgrading

```bash
# Pull latest image
helm upgrade freshrss ./charts/freshrss -n freshrss

# Or with custom values
helm upgrade freshrss ./charts/freshrss -n freshrss -f my-values.yaml
```

## Troubleshooting

### Check pod status
```bash
kubectl get pods -n freshrss
kubectl describe pod -n freshrss <pod-name>
kubectl logs -n freshrss <pod-name>
```

### Check persistent volumes
```bash
kubectl get pvc -n freshrss
```

### Verify service
```bash
kubectl get svc -n freshrss
kubectl port-forward -n freshrss svc/freshrss 8080:80
curl http://localhost:8080
```

## Uninstallation

```bash
# Remove the Helm release
helm uninstall freshrss -n freshrss

# Delete persistent data (WARNING: This deletes all your data!)
kubectl delete pvc -n freshrss freshrss-data freshrss-extensions
```

## Links

- [FreshRSS Official Website](https://freshrss.org/)
- [FreshRSS Documentation](https://freshrss.github.io/FreshRSS/)
- [FreshRSS GitHub Repository](https://github.com/FreshRSS/FreshRSS)
- [FreshRSS Docker Hub](https://hub.docker.com/r/freshrss/freshrss/)
