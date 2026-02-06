# Cloudflare Tunnel

Secure tunnel connecting internal services to Cloudflare's edge network without exposing ports.

## Overview

Deploys [cloudflared](https://github.com/cloudflare/cloudflared) to create an outbound-only tunnel from the cluster to Cloudflare. Traffic reaches internal services through Cloudflare's network, providing DDoS protection and zero-trust access.

```mermaid
flowchart LR
    Internet --> CF[Cloudflare Edge]
    CF --> Tunnel[cloudflared]
    Tunnel --> Services[Internal Services]
```

## Key Features

- **Outbound-only** - No inbound ports required, tunnel connects outward
- **HA deployment** - Multiple replicas for high availability
- **Envoy sidecar** - Optional tracing and observability via envoy proxy
- **1Password integration** - Tunnel credentials from 1Password operator

## Configuration

| Value                   | Description                           | Default       |
| ----------------------- | ------------------------------------- | ------------- |
| `replicaCount`          | Number of tunnel replicas             | `2`           |
| `tunnel.protocol`       | Connection protocol (auto/quic/http2) | `""`          |
| `secret.type`           | Credential source                     | `onepassword` |
| `ingress.routes`        | Route definitions (set in overlay)    | `[]`          |
| `envoy.enabled`         | Enable envoy sidecar for tracing      | `false`       |
| `envoy.tracing.enabled` | Enable OpenTelemetry tracing          | `true`        |

## Ingress Routes

Define routes in your overlay values:

```yaml
ingress:
  routes:
    - hostname: app.example.com
      service: http://app-service.default.svc.cluster.local:80
    - hostname: api.example.com
      service: http://api-gateway.prod.svc.cluster.local:8080
```

## Secret Configuration

Three methods for providing tunnel credentials:

1. **onepassword** - Uses 1Password operator (default)
2. **manual** - Base64-encoded credentials in values
3. **external** - Pre-existing secret in cluster
