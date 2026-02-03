---
name: add-httpcheck-alert
description: Create SigNoz HTTP health check alerts for services. Use when adding uptime monitoring for a new service endpoint.
---

# Add SigNoz HTTP Health Check Alert

## Overview

This skill creates a SigNoz HTTP health check alert that monitors service availability via the `httpcheck.status` metric. The alert fires when a service's health check URL fails 5 consecutive times over 10 minutes.

## Arguments

| Argument    | Required | Description                                    | Example                          |
| ----------- | -------- | ---------------------------------------------- | -------------------------------- |
| `service`   | Yes      | Service name (used in metadata and labels)     | `todo`, `api-gateway`, `claude`  |
| `url`       | Yes      | Full HTTPS URL for the health check endpoint   | `https://todo.jomcgi.dev`        |
| `namespace` | No       | Kubernetes namespace (defaults to service name)| `signoz`, `argocd`               |

## File Structure

Create the alert ConfigMap in the service's overlay directory:

```
overlays/<env>/<service>/<service>-httpcheck-alert.yaml
```

## ConfigMap Structure

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: <service>-httpcheck-alert
  namespace: <namespace>
  labels:
    signoz.io/alert: "true"
  annotations:
    signoz.io/alert-name: "<Service Name> Unreachable"
    signoz.io/severity: "critical"
    signoz.io/notification-channels: "pagerduty-homelab"
data:
  alert.json: |
    {
      ... SigNoz alert JSON ...
    }
```

### Required Labels and Annotations

| Field                                   | Value                     | Purpose                              |
| --------------------------------------- | ------------------------- | ------------------------------------ |
| `labels.signoz.io/alert`                | `"true"`                  | SigNoz alert operator discovers this |
| `annotations.signoz.io/alert-name`      | `"<Service> Unreachable"` | Human-readable alert name            |
| `annotations.signoz.io/severity`        | `"critical"`              | Alert severity level                 |
| `annotations.signoz.io/notification-channels` | `"pagerduty-homelab"` | Notification channel                 |

## SigNoz Alert JSON Format

```json
{
  "alert": "<Service Name> Unreachable",
  "alertType": "METRICS_BASED_ALERT",
  "ruleType": "threshold_rule",
  "broadcastToAll": false,
  "disabled": false,
  "evalWindow": "10m0s",
  "frequency": "2m0s",
  "severity": "critical",
  "labels": {
    "service": "<service>",
    "environment": "production"
  },
  "annotations": {
    "summary": "<Service Name> at <url> is unreachable",
    "description": "HTTP health check has failed 5 consecutive times over 10 minutes. This could indicate the service is down or Cloudflare auth is failing (3xx redirect)."
  },
  "condition": {
    "compositeQuery": {
      "builderQueries": {
        "A": {
          "queryName": "A",
          "dataSource": "metrics",
          "aggregateOperator": "avg",
          "aggregateAttribute": {
            "key": "httpcheck.status",
            "dataType": "float64",
            "type": "Gauge"
          },
          "filters": {
            "items": [
              {
                "key": {"key": "http.url"},
                "op": "=",
                "value": "<url>"
              }
            ]
          }
        }
      },
      "queryType": "builder"
    },
    "op": "<",
    "target": 1,
    "matchType": "5"
  },
  "preferredChannels": ["pagerduty-homelab"]
}
```

### Key Alert Parameters

| Parameter       | Value    | Description                                      |
| --------------- | -------- | ------------------------------------------------ |
| `evalWindow`    | `10m0s`  | Time window to evaluate the condition            |
| `frequency`     | `2m0s`   | How often to check the condition                 |
| `matchType`     | `"5"`    | Alert when condition met 5 times in eval window  |
| `op`            | `<`      | Alert when status is less than target            |
| `target`        | `1`      | httpcheck.status = 1 means success, 0 = failure  |

## Usage Examples

### Example 1: Simple Service (namespace matches service name)

```
/add-httpcheck-alert todo https://todo.jomcgi.dev
```

Creates: `overlays/prod/todo/todo-httpcheck-alert.yaml`

### Example 2: Service with Custom Namespace

```
/add-httpcheck-alert signoz https://signoz.jomcgi.dev signoz
```

Creates: `overlays/cluster-critical/signoz/signoz-httpcheck-alert.yaml`

### Example 3: Service with Health Check Endpoint

```
/add-httpcheck-alert api-gateway https://api.jomcgi.dev/status.json
```

Creates: `overlays/prod/api-gateway/api-gateway-httpcheck-alert.yaml`

## Complete Example

For a service named `myapp` with URL `https://myapp.jomcgi.dev`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: myapp-httpcheck-alert
  namespace: myapp
  labels:
    signoz.io/alert: "true"
  annotations:
    signoz.io/alert-name: "myapp Unreachable"
    signoz.io/severity: "critical"
    signoz.io/notification-channels: "pagerduty-homelab"
data:
  alert.json: |
    {
      "alert": "myapp Unreachable",
      "alertType": "METRICS_BASED_ALERT",
      "ruleType": "threshold_rule",
      "broadcastToAll": false,
      "disabled": false,
      "evalWindow": "10m0s",
      "frequency": "2m0s",
      "severity": "critical",
      "labels": {
        "service": "myapp",
        "environment": "production"
      },
      "annotations": {
        "summary": "myapp at https://myapp.jomcgi.dev is unreachable",
        "description": "HTTP health check has failed 5 consecutive times over 10 minutes. This could indicate the service is down or Cloudflare auth is failing (3xx redirect)."
      },
      "condition": {
        "compositeQuery": {
          "builderQueries": {
            "A": {
              "queryName": "A",
              "dataSource": "metrics",
              "aggregateOperator": "avg",
              "aggregateAttribute": {
                "key": "httpcheck.status",
                "dataType": "float64",
                "type": "Gauge"
              },
              "filters": {
                "items": [
                  {
                    "key": {"key": "http.url"},
                    "op": "=",
                    "value": "https://myapp.jomcgi.dev"
                  }
                ]
              }
            }
          },
          "queryType": "builder"
        },
        "op": "<",
        "target": 1,
        "matchType": "5"
      },
      "preferredChannels": ["pagerduty-homelab"]
    }
```

## Post-Creation Steps

1. Add the alert file to the service's `kustomization.yaml` if not using `resources: ["*.yaml"]`
2. Commit and push the changes
3. ArgoCD will sync the ConfigMap
4. SigNoz alert operator will create the alert rule

## Verification

After ArgoCD syncs, verify the alert was created:

```bash
# Check ConfigMap exists
kubectl get configmap <service>-httpcheck-alert -n <namespace>

# Verify in SigNoz (via MCP)
mcp__signoz__list_alerts
```

## Related Skills

- `/signoz` - Query SigNoz for logs, traces, and alert status
- `/worktree` - Create worktree for making changes
- `/gh-pr` - Create PR after adding the alert
