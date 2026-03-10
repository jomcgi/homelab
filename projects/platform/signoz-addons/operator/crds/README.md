# SigNoz Operator CRDs

Custom Resource Definitions for Kubernetes-native management of SigNoz monitoring resources.

## Overview

The SigNoz Operator provides three CRDs:

| CRD                   | Scope      | Purpose                                      |
| --------------------- | ---------- | -------------------------------------------- |
| `HTTPCheck`           | Namespaced | Synthetic HTTP health checks                 |
| `Alert`               | Namespaced | Alerting rules based on metrics              |
| `NotificationChannel` | Cluster    | Notification targets (PagerDuty, Slack, etc) |

All CRDs use `apiVersion: monitoring.jomcgi.dev/v1alpha1`.

## Quick Start

### HTTPCheck

Monitor HTTP endpoints with automatic health checks:

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: HTTPCheck
metadata:
  name: grafana-health
  namespace: monitoring
spec:
  endpoint: https://grafana.example.com/api/health
  interval: 2m
  timeout: 10s
  expectedStatusCode: 200
```

For Cloudflare Access protected endpoints:

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: HTTPCheck
metadata:
  name: internal-service
  namespace: monitoring
spec:
  endpoint: https://internal.example.com/health
  authSecretRef:
    name: cf-access-credentials
    keys:
      - secretKey: CF_ACCESS_CLIENT_ID
        headerName: CF-Access-Client-Id
      - secretKey: CF_ACCESS_CLIENT_SECRET
        headerName: CF-Access-Client-Secret
```

### Alert

Create alerts from HTTPCheck failures:

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: Alert
metadata:
  name: grafana-down
  namespace: monitoring
spec:
  alertName: Grafana Unreachable
  httpCheckRef:
    name: grafana-health
  condition:
    operator: "<"
    threshold: 1
  consecutiveFailures: 5
  severity: critical
  notificationChannels:
    - pagerduty-oncall
    - slack-alerts
```

Or use custom queries:

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: Alert
metadata:
  name: high-error-rate
  namespace: my-app
spec:
  alertName: High Error Rate
  customQuery:
    query: |
      sum(rate(http_requests_total{status=~"5.."}[5m])) /
      sum(rate(http_requests_total[5m])) * 100
  condition:
    operator: ">"
    threshold: 5
  severity: warning
  notificationChannels:
    - slack-alerts
```

### NotificationChannel

Configure notification targets (cluster-scoped):

**PagerDuty:**

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: NotificationChannel
metadata:
  name: pagerduty-oncall
spec:
  type: pagerduty
  sendResolved: true
  pagerduty:
    routingKeySecretRef:
      name: pagerduty-credentials
      namespace: monitoring
      key: routing-key
```

**Slack:**

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: NotificationChannel
metadata:
  name: slack-alerts
spec:
  type: slack
  sendResolved: true
  slack:
    webhookUrlSecretRef:
      name: slack-webhook
      namespace: monitoring
      key: webhook-url
    channel: "#alerts"
```

**Webhook:**

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: NotificationChannel
metadata:
  name: custom-webhook
spec:
  type: webhook
  webhook:
    url: https://api.example.com/alerts
    httpMethod: POST
    authSecretRef:
      name: webhook-auth
      namespace: monitoring
      key: token
      headerName: Authorization
```

## Secrets

All sensitive data is stored in Kubernetes Secrets:

```yaml
# Cloudflare Access credentials
apiVersion: v1
kind: Secret
metadata:
  name: cf-access-credentials
  namespace: monitoring
type: Opaque
stringData:
  CF_ACCESS_CLIENT_ID: "<service-token-id>"
  CF_ACCESS_CLIENT_SECRET: "<service-token-secret>"
```

```yaml
# PagerDuty routing key
apiVersion: v1
kind: Secret
metadata:
  name: pagerduty-credentials
  namespace: monitoring
type: Opaque
stringData:
  routing-key: "<pagerduty-routing-key>"
```

## kubectl Usage

Short names available:

```bash
# HTTPChecks
kubectl get httpchecks           # or: kubectl get hc
kubectl describe hc grafana-health -n monitoring

# Alerts
kubectl get alerts               # or: kubectl get al
kubectl get al -n monitoring -o wide

# NotificationChannels (cluster-scoped)
kubectl get notificationchannels # or: kubectl get nc
kubectl describe nc pagerduty-oncall
```

## Status Monitoring

All resources provide status information:

```bash
kubectl get hc -n monitoring
# NAME             ENDPOINT                                 STATUS   LAST CHECK
# grafana-health   https://grafana.example.com/api/health   Synced   45ms

kubectl get al -n monitoring
# NAME           ALERT                STATE      SEVERITY
# grafana-down   Grafana Unreachable  inactive   critical
```

### Status Phases

| Phase      | Description                                 |
| ---------- | ------------------------------------------- |
| `Pending`  | Resource created, waiting for initial sync  |
| `Syncing`  | Actively syncing to SigNoz                  |
| `Synced`   | Successfully synced, operational            |
| `Error`    | Sync failed, check `.status.errorMessage`   |
| `Disabled` | Resource disabled via `spec.disabled: true` |

## Common Patterns

### Service Co-location

Define monitoring alongside your application:

```
overlays/prod/my-app/
├── application.yaml
├── values.yaml
├── httpcheck.yaml          # Health check for this service
└── alert.yaml              # Alerts for this service
```

### Shared Notification Channels

NotificationChannels are cluster-scoped and reusable:

```yaml
# Deploy once in monitoring namespace
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: NotificationChannel
metadata:
  name: team-platform-slack
spec:
  type: slack
  slack:
    webhookUrlSecretRef:
      name: platform-slack-webhook
      namespace: monitoring
      key: webhook-url
    channel: "#platform-alerts"
---
# Reference from any namespace
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: Alert
metadata:
  name: my-alert
  namespace: my-app
spec:
  alertName: My Service Alert
  notificationChannels:
    - team-platform-slack # References cluster-scoped resource
  # ...
```

### Temporary Disable

Disable resources without deleting:

```bash
kubectl patch hc grafana-health -n monitoring \
  --type merge -p '{"spec":{"disabled":true}}'

kubectl patch al grafana-down -n monitoring \
  --type merge -p '{"spec":{"disabled":true}}'
```

## API Reference

For complete field documentation, see [API_REFERENCE.md](./API_REFERENCE.md).

## Design Decisions

1. **Namespaced HTTPCheck and Alert** - Services define monitoring alongside deployments (co-location principle)
2. **Cluster-scoped NotificationChannel** - Shared infrastructure, avoid duplication
3. **Secret references** - Sensitive credentials in Kubernetes Secrets
4. **HTTPCheck references in Alerts** - Direct references avoid manual query construction
5. **Short names** - Quick kubectl access (`hc`, `al`, `nc`)
