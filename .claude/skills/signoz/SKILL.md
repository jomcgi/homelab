---
name: signoz
description: Use when debugging issues, investigating errors, checking service health, or analyzing performance. Provides access to logs, traces, metrics, and alerts via MCP.
---

# SigNoz Observability

## CRITICAL: Time Format Requirements

**Different functions require different time units. Using the wrong unit will return no results.**

| Function Type   | Time Unit    | Example               |
| --------------- | ------------ | --------------------- |
| Logs            | milliseconds | `1704067200000`       |
| Traces (search) | milliseconds | `1704067200000`       |
| Services        | nanoseconds  | `1704067200000000000` |
| Top operations  | nanoseconds  | `1704067200000000000` |

**Getting current timestamps:**

```javascript
// Milliseconds (for logs, trace search)
Date.now();

// Nanoseconds (for services, top operations)
Date.now() * 1000000;
```

## Overview

SigNoz is the cluster's observability platform providing unified metrics, logs, and traces. Access is available via MCP functions - no kubectl port-forward needed.

## Debugging Workflow

When investigating issues, follow this order:

1. **Check alerts** - Are there active alerts?
2. **Find error logs** - What errors occurred in the time range?
3. **Trace analysis** - Follow request flow through services
4. **Service health** - Check top operations and latency

## Available MCP Functions

### Service Discovery

```
mcp__signoz__list_services
```

Lists all services reporting to SigNoz. Use this first to discover service names.

**Parameters:** `start`, `end` (nanoseconds, optional - defaults to last 24h)

### Logs

```
mcp__signoz__get_error_logs
```

Find ERROR or FATAL severity logs.

**Parameters:**

- `start`, `end` (milliseconds) - Required
- `service` - Optional service filter
- `limit` - Max results (default: 100)

```
mcp__signoz__search_logs_by_service
```

Search logs for a specific service.

**Parameters:**

- `service` - Required
- `start`, `end` (milliseconds) - Required
- `severity` - DEBUG, INFO, WARN, ERROR, FATAL
- `searchText` - Text to search in log body
- `limit` - Max results (default: 100)

### Traces

```
mcp__signoz__search_traces_by_service
```

Find traces for a service with optional filters.

**Parameters:**

- `service` - Required
- `start`, `end` (milliseconds) - Optional (defaults to last 24h)
- `operation` - Filter by operation name
- `error` - Filter by error status (true/false)
- `minDuration`, `maxDuration` - Duration filters (nanoseconds)
- `limit` - Max results (default: 100)

```
mcp__signoz__get_trace_details
```

Get comprehensive trace information including all spans.

**Parameters:**

- `traceId` - Required
- `start`, `end` (milliseconds) - Optional
- `includeSpans` - Include span details (default: true)

```
mcp__signoz__get_trace_span_hierarchy
```

Get span relationships and hierarchy for a trace.

**Parameters:**

- `traceId` - Required
- `start`, `end` (milliseconds) - Optional

```
mcp__signoz__get_trace_error_analysis
```

Analyze error patterns in traces.

**Parameters:**

- `start`, `end` (milliseconds) - Optional
- `service` - Optional service filter

### Alerts

```
mcp__signoz__list_alerts
```

List all active alert rules. No parameters required.

```
mcp__signoz__get_alert
```

Get details of a specific alert rule.

**Parameters:**

- `ruleId` - Required

```
mcp__signoz__get_logs_for_alert
```

Get logs related to a specific alert.

**Parameters:**

- `alertId` - Required
- `timeRange` - e.g., '1h', '30m' (default: '1h')
- `limit` - Max results (default: 100)

### Metrics

```
mcp__signoz__list_metric_keys
```

List available metric keys. No parameters required.

```
mcp__signoz__search_metric_keys
```

Search metrics by text.

**Parameters:**

- `searchText` - Required

```
mcp__signoz__get_service_top_operations
```

Get top operations for a service (latency, throughput).

**Parameters:**

- `service` - Required
- `start`, `end` (nanoseconds) - Optional

### Dashboards & Views

```
mcp__signoz__list_dashboards
```

List all dashboards. No parameters required.

```
mcp__signoz__get_dashboard
```

Get full dashboard configuration.

**Parameters:**

- `uuid` - Dashboard UUID

```
mcp__signoz__list_log_views
```

List saved log views. No parameters required.

```
mcp__signoz__get_log_view
```

Get log view configuration.

**Parameters:**

- `viewId` - Required

## Common Debugging Scenarios

### "Service is returning errors"

1. Find error logs:

   ```
   mcp__signoz__get_error_logs(start, end, service="my-service")
   ```

2. Search for error traces:

   ```
   mcp__signoz__search_traces_by_service(service="my-service", error="true")
   ```

3. Get trace details for specific error:
   ```
   mcp__signoz__get_trace_details(traceId="abc123")
   ```

### "Service is slow"

1. Check top operations:

   ```
   mcp__signoz__get_service_top_operations(service="my-service")
   ```

2. Find slow traces:
   ```
   mcp__signoz__search_traces_by_service(service="my-service", minDuration="1000000000")
   ```
   (minDuration in nanoseconds = 1 second)

### "What's happening in the cluster?"

1. List services:

   ```
   mcp__signoz__list_services()
   ```

2. Check alerts:

   ```
   mcp__signoz__list_alerts()
   ```

3. Get recent errors across all services:
   ```
   mcp__signoz__get_error_logs(start, end)
   ```

## Common Service Names

| Service         | Description                     |
| --------------- | ------------------------------- |
| `cui-server`    | Claude web interface API server |
| `argocd-server` | ArgoCD GitOps controller        |
| `linkerd-*`     | Service mesh components         |

Use `mcp__signoz__list_services()` to discover all available services.
