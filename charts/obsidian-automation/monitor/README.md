# Obsidian Sync Monitor

A Go application that monitors Obsidian sync status and performs synthetic tests to ensure the automation service is functioning correctly.

## Features

- **Sync Status Monitoring**: Continuously monitors Obsidian Sync connection status
- **Synthetic Testing**: Creates and verifies test notes to ensure end-to-end functionality
- **Health Checks**: Provides `/health` and `/ready` endpoints for Kubernetes probes
- **Prometheus Metrics**: Exports comprehensive metrics for observability
- **OpenTelemetry Tracing**: Distributed tracing support for request flows
- **Structured Logging**: JSON logs with correlation IDs

## Metrics

The monitor exports the following Prometheus metrics:

- `obsidian_sync_connected`: Gauge (0/1) for sync connection status
- `obsidian_sync_last_success_timestamp`: Gauge for last successful sync
- `obsidian_api_request_duration_seconds`: Histogram for API latencies
- `obsidian_api_requests_total`: Counter for API requests by endpoint
- `obsidian_synthetic_test_success`: Gauge (0/1) for synthetic test status
- `obsidian_authentication_attempts_total`: Counter for auth attempts
- `obsidian_sync_failures_total`: Counter for sync failures by type
- `obsidian_pending_changes`: Gauge for pending changes count
- `obsidian_last_synthetic_test_timestamp`: Gauge for last test execution

## Configuration

Environment variables:

- `OBSIDIAN_API_KEY`: API key for Obsidian REST API (required)
- `OTLP_ENDPOINT`: OpenTelemetry OTLP endpoint (optional)

Command-line flags:

- `--metrics-addr`: Metrics server address (default: `:8080`)
- `--probe-addr`: Health probe server address (default: `:8081`)
- `--obsidian-api-url`: Obsidian REST API URL (default: `http://localhost:27124`)
- `--check-interval`: Sync status check interval (default: `5m`)
- `--synthetic-interval`: Synthetic test interval (default: `5m`)
- `--log-level`: Log level (default: `info`)

## Usage

```bash
# Run locally
go run main.go --obsidian-api-url=http://localhost:27124

# Build Docker image
docker build -t obsidian-sync-monitor .

# Run container
docker run -p 8080:8080 -p 8081:8081 \
  -e OBSIDIAN_API_KEY=your-api-key \
  obsidian-sync-monitor
```

## Kubernetes Integration

The monitor is designed to run as a sidecar container alongside the main Obsidian container in a Kubernetes pod. It provides health and readiness probes that can be used by Kubernetes to manage the pod lifecycle.

Example sidecar configuration:

```yaml
- name: sync-monitor
  image: ghcr.io/jomcgi/obsidian-automation-sync-monitor:latest
  ports:
    - containerPort: 8080
      name: metrics
    - containerPort: 8081
      name: probes
  env:
    - name: OBSIDIAN_API_KEY
      valueFrom:
        secretKeyRef:
          name: obsidian-api-credentials
          key: api-key
  livenessProbe:
    httpGet:
      path: /health
      port: 8081
    initialDelaySeconds: 30
    periodSeconds: 30
  readinessProbe:
    httpGet:
      path: /ready
      port: 8081
    initialDelaySeconds: 10
    periodSeconds: 10
```

## Development

```bash
# Install dependencies
go mod download

# Run tests
go test -v ./...

# Run linter
golangci-lint run

# Build binary
go build -o sync-monitor main.go
```

## Architecture

The monitor consists of three main components:

1. **Sync Status Checker**: Periodically calls the Obsidian API to check sync status
2. **Synthetic Test Runner**: Creates test notes to verify end-to-end functionality
3. **Health Monitor**: Provides health and readiness status for Kubernetes

All components run concurrently and communicate through shared metrics and status variables.

## License

Licensed under the Apache License, Version 2.0.