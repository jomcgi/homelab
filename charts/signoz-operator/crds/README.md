# SigNoz Operator CRDs

This directory contains Custom Resource Definitions (CRDs) for the SigNoz Operator, enabling Kubernetes-native management of SigNoz monitoring resources.

## Overview

The SigNoz Operator provides three CRDs:

| CRD                   | Scope      | Purpose                                      |
| --------------------- | ---------- | -------------------------------------------- |
| `HTTPCheck`           | Namespaced | Synthetic HTTP health checks                 |
| `Alert`               | Namespaced | Alerting rules based on metrics              |
| `NotificationChannel` | Cluster    | Notification targets (PagerDuty, Slack, etc) |

All CRDs use `apiVersion: monitoring.jomcgi.dev/v1alpha1`.

## HTTPCheck

Defines synthetic HTTP health checks that SigNoz will execute at regular intervals.

### Spec Fields

| Field                | Type              | Required | Default | Description                              |
| -------------------- | ----------------- | -------- | ------- | ---------------------------------------- |
| `endpoint`           | string            | Yes      | -       | URL to check (must start with http(s)://) |
| `method`             | enum              | No       | GET     | HTTP method (GET, POST, HEAD)            |
| `expectedStatusCode` | integer           | No       | 200     | Expected response status code            |
| `interval`           | string            | No       | 2m      | Check frequency (e.g., "30s", "2m")      |
| `timeout`            | string            | No       | 10s     | Request timeout                          |
| `headers`            | map[string]string | No       | -       | Custom HTTP headers                      |
| `body`               | string            | No       | -       | Request body for POST requests           |
| `authSecretRef`      | object            | No       | -       | Reference to Secret with auth credentials|
| `insecureSkipVerify` | boolean           | No       | false   | Skip TLS verification                    |
| `labels`             | map[string]string | No       | -       | Labels for grouping/filtering            |
| `disabled`           | boolean           | No       | false   | Temporarily disable the check            |

### Example

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: HTTPCheck
metadata:
  name: grafana-health
  namespace: monitoring
spec:
  endpoint: https://grafana.example.com/api/health
  method: GET
  expectedStatusCode: 200
  interval: 2m
  timeout: 10s
  labels:
    service: grafana
    environment: production
  # For Cloudflare Access protected endpoints
  authSecretRef:
    name: cf-access-credentials
    keys:
      - secretKey: CF_ACCESS_CLIENT_ID
        headerName: CF-Access-Client-Id
      - secretKey: CF_ACCESS_CLIENT_SECRET
        headerName: CF-Access-Client-Secret
```

### Status

```yaml
status:
  phase: Synced              # Pending, Syncing, Synced, Error, Disabled
  signozId: "abc123"         # ID in SigNoz
  lastSyncTime: "2024-01-15T10:30:00Z"
  lastCheckTime: "2024-01-15T10:32:00Z"
  lastCheckResult: Success   # Success, Failure, Unknown
  lastResponseTime: 45       # Response time in ms
```

## Alert

Defines alerting rules that evaluate metrics and trigger notifications.

### Spec Fields

| Field                  | Type     | Required | Default | Description                              |
| ---------------------- | -------- | -------- | ------- | ---------------------------------------- |
| `alertName`            | string   | Yes      | -       | Display name for the alert               |
| `description`          | string   | No       | -       | Detailed description                     |
| `summary`              | string   | No       | -       | Short summary for notifications          |
| `httpCheckRef`         | object   | No*      | -       | Reference to HTTPCheck to alert on       |
| `customQuery`          | object   | No*      | -       | Custom PromQL/ClickHouse query           |
| `condition`            | object   | Yes      | -       | Alert trigger condition                  |
| `evalWindow`           | string   | No       | 5m      | Evaluation time window                   |
| `frequency`            | string   | No       | 1m      | Evaluation frequency                     |
| `consecutiveFailures`  | integer  | No       | 1       | Required consecutive failures            |
| `severity`             | enum     | No       | warning | critical, warning, info                  |
| `notificationChannels` | []string | No       | -       | NotificationChannel names to notify      |
| `labels`               | map      | No       | -       | Labels for grouping/routing              |
| `annotations`          | map      | No       | -       | Additional metadata                      |
| `disabled`             | boolean  | No       | false   | Temporarily disable                      |
| `runbookUrl`           | string   | No       | -       | Link to response documentation           |

*Either `httpCheckRef` or `customQuery` should be specified.

### Condition Object

| Field       | Type   | Required | Default | Description                          |
| ----------- | ------ | -------- | ------- | ------------------------------------ |
| `operator`  | enum   | Yes      | -       | >, >=, <, <=, ==, !=                 |
| `threshold` | number | Yes      | -       | Value to compare against             |
| `matchType` | enum   | No       | once    | once, always, onAverage, inTotal     |

### Example: HTTPCheck Alert

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: Alert
metadata:
  name: grafana-down
  namespace: monitoring
spec:
  alertName: Grafana Unreachable
  description: Grafana health check has been failing
  httpCheckRef:
    name: grafana-health
  condition:
    operator: "<"
    threshold: 1
    matchType: always
  evalWindow: 10m
  frequency: 2m
  consecutiveFailures: 5
  severity: critical
  notificationChannels:
    - pagerduty-oncall
    - slack-alerts
  labels:
    service: grafana
    team: platform
  runbookUrl: https://wiki.example.com/runbooks/grafana-down
```

### Example: Custom Query Alert

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: Alert
metadata:
  name: high-error-rate
  namespace: my-app
spec:
  alertName: High Error Rate
  description: Application error rate exceeds 5%
  customQuery:
    query: |
      sum(rate(http_requests_total{status=~"5.."}[5m])) /
      sum(rate(http_requests_total[5m])) * 100
    queryType: promql
  condition:
    operator: ">"
    threshold: 5
  evalWindow: 5m
  severity: warning
  notificationChannels:
    - slack-alerts
```

### Status

```yaml
status:
  phase: Synced
  signozId: "def456"
  lastSyncTime: "2024-01-15T10:30:00Z"
  alertState: inactive    # inactive, pending, firing
  lastFiredTime: "2024-01-14T15:45:00Z"
```

## NotificationChannel

Defines notification targets for alerts. This is a cluster-scoped resource.

### Spec Fields

| Field          | Type    | Required | Default | Description                              |
| -------------- | ------- | -------- | ------- | ---------------------------------------- |
| `type`         | enum    | Yes      | -       | pagerduty, webhook, slack, email, opsgenie, msteams |
| `sendResolved` | boolean | No       | true    | Send notification when alert resolves    |
| `pagerduty`    | object  | No*      | -       | PagerDuty configuration                  |
| `webhook`      | object  | No*      | -       | Webhook configuration                    |
| `slack`        | object  | No*      | -       | Slack configuration                      |
| `email`        | object  | No*      | -       | Email configuration                      |
| `opsgenie`     | object  | No*      | -       | OpsGenie configuration                   |
| `msteams`      | object  | No*      | -       | Microsoft Teams configuration            |

*The corresponding configuration object is required based on `type`.

### Example: PagerDuty

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
    severity: error
```

### Example: Slack

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
    username: SigNoz Alerts
    iconEmoji: ":warning:"
```

### Example: Webhook

```yaml
apiVersion: monitoring.jomcgi.dev/v1alpha1
kind: NotificationChannel
metadata:
  name: custom-webhook
spec:
  type: webhook
  sendResolved: true
  webhook:
    url: https://api.example.com/alerts
    httpMethod: POST
    authSecretRef:
      name: webhook-auth
      namespace: monitoring
      key: token
      headerName: Authorization
    headers:
      Content-Type: application/json
```

### Status

```yaml
status:
  phase: Synced
  signozId: "ghi789"
  lastSyncTime: "2024-01-15T10:30:00Z"
  lastTestTime: "2024-01-15T10:30:05Z"
  lastTestResult: Success
```

## Secret References

All sensitive data (API keys, tokens, webhooks) are stored in Kubernetes Secrets and referenced by the CRDs.

### Cloudflare Access Credentials

```yaml
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

### PagerDuty Routing Key

```yaml
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

Short names are available for convenience:

```bash
# HTTPChecks
kubectl get httpchecks           # or: kubectl get hc
kubectl get hc -n monitoring

# Alerts
kubectl get alerts               # or: kubectl get al
kubectl get al -n monitoring

# NotificationChannels (cluster-scoped)
kubectl get notificationchannels # or: kubectl get nc
kubectl get notifchan
```

## Status Phases

All resources follow the same phase lifecycle:

| Phase      | Description                                          |
| ---------- | ---------------------------------------------------- |
| `Pending`  | Resource created, waiting for initial sync           |
| `Syncing`  | Actively syncing to SigNoz                           |
| `Synced`   | Successfully synced, SigNoz ID assigned              |
| `Error`    | Sync failed, see `errorMessage` for details          |
| `Disabled` | Resource disabled via `spec.disabled: true`          |

## Design Decisions

1. **Namespaced HTTPCheck and Alert**: Services can define their own monitoring alongside their deployments, following the principle of co-location.

2. **Cluster-scoped NotificationChannel**: Notification targets (PagerDuty, Slack) are typically shared infrastructure, avoiding duplication across namespaces.

3. **Secret references**: Sensitive credentials are stored in Kubernetes Secrets, following security best practices.

4. **HTTPCheck reference in Alerts**: Alerts can reference HTTPChecks directly, automatically using the check's status metric without requiring manual query construction.

5. **Short names**: `hc`, `al`, and `nc` provide quick kubectl access.

6. **Printer columns**: Key status information visible in `kubectl get` output.
