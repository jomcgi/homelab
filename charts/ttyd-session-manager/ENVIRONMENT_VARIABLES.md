# Claude Code Environment Variables for TTYD Session Manager

This document outlines the recommended environment variables for Claude Code sessions running in ttyd-session-manager pods.

## Essential (Authentication)

### CLAUDE_CODE_OAUTH_TOKEN
**Required for Claude Code authentication**
- Source: 1Password secret at `op://k8s-homelab/ttyd-session-manager/claude_code_oauth_token`
- Mount as environment variable from Kubernetes secret

```yaml
- name: CLAUDE_CODE_OAUTH_TOKEN
  valueFrom:
    secretKeyRef:
      name: ttyd-session-manager-claude
      key: oauth_token
```

---

## Privacy & Security (Disable External Telemetry)

### DISABLE_TELEMETRY
**Disable Anthropic's Statsig telemetry**
- Value: `true`
- Prevents external telemetry data from leaving the cluster

### DISABLE_ERROR_REPORTING
**Disable Sentry error reporting**
- Value: `true`
- Prevents error reports from being sent to external Sentry

### DISABLE_AUTOUPDATER
**Disable automatic updates**
- Value: `true`
- Container image should control Claude Code version, not auto-updater

```yaml
- name: DISABLE_TELEMETRY
  value: "true"
- name: DISABLE_ERROR_REPORTING
  value: "true"
- name: DISABLE_AUTOUPDATER
  value: "true"
```

---

## Internal Observability (OpenTelemetry → SigNoz)

Route traces, metrics, and logs to SigNoz OTEL collector in the cluster.

### OTEL_RESOURCE_ATTRIBUTES

```yaml
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://signoz-otel-collector.signoz.svc.cluster.local:4317"
- name: OTEL_SERVICE_NAME
  value: "claude-code-session"
- name: OTEL_TRACES_EXPORTER
  value: "otlp"
- name: OTEL_METRICS_EXPORTER
  value: "otlp"
- name: OTEL_LOGS_EXPORTER
  value: "otlp"
- name: OTEL_RESOURCE_ATTRIBUTES
  value: "session.id=$(SESSION_ID),"
```

---

## User Experience Improvements

```yaml
- name: CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR
  value: "true"
- name: CLAUDE_CODE_DISABLE_TERMINAL_TITLE
  value: "true"
- name: DISABLE_COST_WARNINGS
  value: "true"
- name: DISABLE_NON_ESSENTIAL_MODEL_CALLS
  value: "true"
```

---

## Optional (Configurable via Helm Values)

These can be exposed in `values.yaml` for flexibility:

### HTTP_PROXY / HTTPS_PROXY / NO_PROXY
**Proxy configuration**
- Only needed if cluster uses HTTP proxies

---

## Implementation Location

Add these environment variables to the `ttyd` container in:
- **File**: `charts/ttyd-session-manager/backend/main.go`
- **Location**: Lines 244-269 (ttyd container's `Env` slice)
