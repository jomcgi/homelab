# n8n Obsidian API

FastAPI service providing type-safe, restricted access to the [Obsidian Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) for n8n workflows.

## Overview

This service acts as a smart proxy between n8n and Obsidian, providing:

- **Type-safe Python interface** - Pydantic models for all API interactions
- **Path restrictions** - Write operations limited to `/n8n/` folder, reads allowed vault-wide
- **Domain-specific endpoints** - Simple, high-level APIs tailored for n8n workflows
- **Built-in observability** - OpenTelemetry tracing for all operations
- **Secure by design** - Non-root container, read-only filesystem, minimal attack surface

## Architecture

```
┌─────────┐         ┌────────────────────┐         ┌──────────────────┐         ┌──────────────┐
│   n8n   │────────>│ n8n-obsidian-api   │────────>│ Cloudflare       │────────>│   Obsidian   │
│Workflow │  HTTP   │   (This Service)   │  HTTPS  │ Tunnel + Access  │  HTTP   │ REST API     │
└─────────┘         └────────────────────┘         └──────────────────┘         └──────────────┘
                            │                              │
                            │                              │ Injects Obsidian
                            │ gRPC (OTLP)                  │ API credentials
                            ▼                              ▼
                    ┌────────────────┐
                    │  OpenTelemetry │
                    │    Collector   │
                    └────────────────┘
```

### Authentication Flow

1. **n8n → This Service**: Standard HTTP requests within cluster
2. **This Service → Cloudflare**: Uses service token headers (`CF-Access-Client-Id`, `CF-Access-Client-Secret`)
3. **Cloudflare Access**: Validates service token, injects Obsidian API credentials
4. **Cloudflare → Obsidian**: Authenticated request with Obsidian API key

This architecture means **we don't manage Obsidian API keys** - Cloudflare handles that for us!

### Why This Design?

Instead of having n8n directly interact with the Obsidian API:
1. **Simplify n8n workflows** - Clean HTTP endpoints vs. complex API calls
2. **Enforce security** - Path restrictions enforced server-side
3. **Type safety** - Python's type system catches errors at dev time
4. **Observability** - All operations traced automatically
5. **Business logic** - Complex operations encapsulated in service
6. **Leverage Cloudflare** - Authentication and credential injection handled by Cloudflare Access

## API Endpoints

### Create or Update Note

```http
POST /notes/create
Content-Type: application/json

{
  "path": "n8n/workflows/data-sync.md",
  "content": "# Data Sync Workflow\n\nStatus: Active"
}
```

### Append to Note

```http
POST /notes/append
Content-Type: application/json

{
  "path": "n8n/logs/workflow-runs.md",
  "content": "\n- [2024-01-15] Workflow executed successfully"
}
```

### Append to Section

```http
POST /notes/append-to-section
Content-Type: application/json

{
  "path": "n8n/project-notes.md",
  "heading": "Tasks",
  "content": "\n- [ ] Review API integration"
}
```

### Update Frontmatter

```http
POST /notes/update-frontmatter
Content-Type: application/json

{
  "path": "n8n/workflows/sync.md",
  "key": "status",
  "value": "completed"
}
```

### Read Note

```http
GET /notes/n8n/workflows/sync.md
```

### Delete Note

```http
DELETE /notes/n8n/temp/scratch.md
```

## Path Restrictions

### Write Operations (PUT, POST, PATCH, DELETE)

**ONLY allowed in `/n8n/` directory**

```python
✅ "n8n/workflows/test.md"      # Allowed
✅ "n8n/logs/run-history.md"   # Allowed
❌ "personal/notes.md"          # Forbidden
❌ "Projects/work.md"           # Forbidden
```

### Read Operations (GET)

**Allowed anywhere in vault**

```python
✅ "n8n/workflows/test.md"      # Allowed
✅ "personal/notes.md"          # Allowed
✅ "Projects/work.md"           # Allowed
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OBSIDIAN_API_URL` | URL of Obsidian API via Cloudflare Tunnel | `https://obsidian.jomcgi.dev` | Yes |
| `CLOUDFLARE_CLIENT_ID` | Cloudflare service token client ID | - | Yes |
| `CLOUDFLARE_CLIENT_SECRET` | Cloudflare service token client secret | - | Yes |
| `SERVICE_HOST` | Host to bind service to | `0.0.0.0` | No |
| `SERVICE_PORT` | Port to listen on | `8080` | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `OTEL_ENABLED` | Enable OpenTelemetry tracing | `true` | No |
| `OTEL_SERVICE_NAME` | Service name in traces | `n8n-obsidian-api` | No |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint for traces | - | No |

### Helm Values

See [`charts/n8n-obsidian-api/values.yaml`](../../charts/n8n-obsidian-api/values.yaml) for full configuration options.

Key settings:

```yaml
config:
  # Obsidian API URL via Cloudflare Tunnel
  obsidianApiUrl: "https://obsidian.jomcgi.dev"

  # Cloudflare service token credentials
  cloudflare:
    secretName: "cloudflare-service-token"
    clientIdKey: "client-id"
    clientSecretKey: "client-secret"

  opentelemetry:
    enabled: true
    otlpEndpoint: "http://signoz-otel-collector:4317"

# 1Password integration for Cloudflare service token
onePassword:
  enabled: true
  itemPath: "vaults/homelab/items/cloudflare-service-token-obsidian"
```

## Deployment

### Prerequisites

1. **Obsidian with Local REST API plugin** (already configured)
   - Running at `obsidian.jomcgi.dev` via Cloudflare Tunnel
   - Cloudflare Access configured to inject Obsidian API credentials

2. **Cloudflare Service Token** (for bypassing Access)
   - Create a service token in Cloudflare Access for the Obsidian application
   - Note the `Client ID` and `Client Secret`

3. **1Password Operator** (for secrets management)
   - Create item in 1Password: `vaults/homelab/items/cloudflare-service-token-obsidian`
   - Add fields:
     - `client-id`: Cloudflare service token client ID
     - `client-secret`: Cloudflare service token client secret

4. **ArgoCD** (for GitOps deployment)

### Deploy to Kubernetes

The service is deployed via ArgoCD using GitOps:

1. **Commit your changes** to the repository

2. **ArgoCD auto-sync** will deploy the service:
   ```bash
   kubectl get application -n argocd n8n-obsidian-api
   ```

3. **Verify deployment**:
   ```bash
   kubectl get pods -n n8n -l app.kubernetes.io/name=n8n-obsidian-api
   ```

4. **Check service health**:
   ```bash
   kubectl port-forward -n n8n svc/n8n-obsidian-api 8080:80
   curl http://localhost:8080/
   ```

### Manual Deployment (Development)

```bash
# Build Docker image
docker build -t n8n-obsidian-api:latest services/n8n-obsidian-api/

# Run locally (pointing to production Obsidian via Cloudflare)
docker run -p 8080:8080 \
  -e OBSIDIAN_API_URL=https://obsidian.jomcgi.dev \
  -e CLOUDFLARE_CLIENT_ID=your-client-id \
  -e CLOUDFLARE_CLIENT_SECRET=your-client-secret \
  n8n-obsidian-api:latest
```

## Development

### Local Setup

```bash
cd services/n8n-obsidian-api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Set environment variables
export OBSIDIAN_API_URL="https://obsidian.jomcgi.dev"
export CLOUDFLARE_CLIENT_ID="your-client-id"
export CLOUDFLARE_CLIENT_SECRET="your-client-secret"

# Run development server
uvicorn app.main:app --reload --port 8080
```

### Running Tests

```bash
pytest
pytest --cov=app tests/
```

### Code Quality

```bash
# Format and lint
ruff check app/
ruff format app/
```

## Usage Examples

### n8n HTTP Request Node

```json
{
  "method": "POST",
  "url": "http://n8n-obsidian-api/notes/create",
  "body": {
    "path": "n8n/{{ $workflow.name }}/{{ $today }}.md",
    "content": "# {{ $workflow.name }}\n\nExecuted at: {{ $now }}"
  }
}
```

### Curl

```bash
# Create a note
curl -X POST http://n8n-obsidian-api/notes/create \
  -H "Content-Type: application/json" \
  -d '{
    "path": "n8n/test.md",
    "content": "# Test Note\n\nCreated via API"
  }'

# Read a note
curl http://n8n-obsidian-api/notes/n8n/test.md

# Append to a note
curl -X POST http://n8n-obsidian-api/notes/append \
  -H "Content-Type: application/json" \
  -d '{
    "path": "n8n/test.md",
    "content": "\n\nAppended content"
  }'
```

## Observability

### OpenTelemetry Tracing

All API operations are automatically traced. Traces include:

- **HTTP requests** - Request/response details
- **Obsidian API calls** - Path, operation type
- **Errors** - Stack traces and error context

View traces in SigNoz or your configured OTLP backend.

### Metrics

Standard FastAPI metrics are available:
- Request count
- Request duration
- Active requests
- HTTP status codes

### Logs

Structured JSON logs at configurable levels:
- `DEBUG` - Detailed operation logs
- `INFO` - Standard operation logs (default)
- `WARNING` - Warnings and recoverable errors
- `ERROR` - Errors requiring attention

## Security

### Container Security

- **Non-root user** - Runs as UID 1000
- **Read-only filesystem** - No write access to container FS
- **No privilege escalation** - `allowPrivilegeEscalation: false`
- **Dropped capabilities** - All Linux capabilities dropped
- **Seccomp profile** - RuntimeDefault profile applied

### Network Security

- **No direct internet access** - Internal cluster communication only
- **Service-to-service** - Accessed via n8n within cluster
- **Optional API key** - Can add authentication if needed

### Path Validation

All write operations validate paths start with `n8n/`:

```python
# This is enforced in app/clients/obsidian.py
def _validate_write_path(self, path: str) -> None:
    normalized = Path(path).as_posix().lstrip("/")
    if not normalized.startswith("n8n/"):
        raise PathRestrictionError(...)
```

## Troubleshooting

### Service won't start

Check logs:
```bash
kubectl logs -n n8n -l app.kubernetes.io/name=n8n-obsidian-api
```

Common issues:
- Missing Cloudflare credentials - Check 1Password secret sync
- Cannot reach Obsidian API - Verify `OBSIDIAN_API_URL` points to `https://obsidian.jomcgi.dev`
- Cloudflare Access errors - Verify service token is valid

### Path restriction errors

Error: `PathRestrictionError: Write operations only allowed in /n8n/`

**Fix**: Ensure paths start with `n8n/`:
```json
{
  "path": "n8n/my-note.md",  // ✅ Correct
  "path": "my-note.md"        // ❌ Wrong
}
```

### Obsidian API connection fails

1. **Check Cloudflare service token** is valid and not expired
2. **Verify service token** has access to the Obsidian application in Cloudflare Access
3. **Test connection** manually:
   ```bash
   curl https://obsidian.jomcgi.dev/ \
     -H "CF-Access-Client-Id: YOUR_CLIENT_ID" \
     -H "CF-Access-Client-Secret: YOUR_CLIENT_SECRET"
   ```
4. **Check Cloudflare Access logs** for authentication failures

## API Documentation

Interactive API documentation available at:
- **Swagger UI**: `http://n8n-obsidian-api/docs`
- **ReDoc**: `http://n8n-obsidian-api/redoc`

## License

Part of the homelab project.
