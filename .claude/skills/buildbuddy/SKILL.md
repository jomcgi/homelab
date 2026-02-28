---
name: buildbuddy
description: Use when debugging failed CI/CD jobs, analyzing build logs, or investigating GitHub Actions failures. Access BuildBuddy remote build execution and caching service for detailed build insights.
---

# BuildBuddy - Remote Build Execution & CI Debugging

## Authentication

The BuildBuddy API requires the `BUILDBUDDY_API_KEY` environment variable.

**API Header:** `x-buildbuddy-api-key: $BUILDBUDDY_API_KEY`

Reference: [BuildBuddy Authentication Guide](https://www.buildbuddy.io/docs/guide-auth/)

## API Endpoints

Base URL: `https://jomcgi.buildbuddy.io/api/v1`

All requests use **POST** with JSON body containing a selector:

```json
{ "selector": { "invocation_id": "<invocation_id>" } }
```

Available endpoints:

- `/GetInvocation` - Retrieve invocation details
- `/GetLog` - Fetch build logs
- `/GetTarget` - Access target information
- `/GetAction` - Get action details
- `/GetFile` - Download files using URIs

Reference: [BuildBuddy API Documentation](https://www.buildbuddy.io/docs/enterprise-api/)

### API Workflow

```
┌──────────────────────────────────────────────┐
│  GitHub Actions Job Fails                     │
│  - CI build error in PR                       │
│  - BuildBuddy URL in check logs              │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Extract Invocation ID                        │
│  From URL: https://jomcgi.buildbuddy.io/        │
│            invocation/<id>                    │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  API: POST /GetInvocation                     │
│  Headers: x-buildbuddy-api-key               │
│  Body: {"selector": {"invocation_id": "..."}}│
│  Returns: build metadata, status, duration   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  API: POST /GetLog                            │
│  Returns: stdout/stderr, error messages      │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Parse Errors and Identify Root Cause        │
│  - Compilation errors                        │
│  - Test failures                             │
│  - Linter issues                             │
└──────────────────────────────────────────────┘
```

## Debugging Failed GitHub Actions

### Quick Start

```bash
# 1. Get invocation ID from PR checks
INVOCATION_ID=$(gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link' | grep -o '[^/]*$' | head -1)

# 2. Get invocation details
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
  https://jomcgi.buildbuddy.io/api/v1/GetInvocation

# 3. Get build logs
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
  https://jomcgi.buildbuddy.io/api/v1/GetLog
```

## API Request Pattern

All endpoints use the same request format:

```bash
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"selector":{"invocation_id":"<INVOCATION_ID>"}}' \
  https://jomcgi.buildbuddy.io/api/v1/<ENDPOINT>
```

### Useful jq Filters by Endpoint

| Endpoint | jq Filter | Returns |
| --- | --- | --- |
| `GetInvocation` | `'{success: .invocation.success, command: .invocation.command, duration_ms: .invocation.duration_millis}'` | Build summary |
| `GetInvocation` | `'{repo: .invocation.repo_url, commit: .invocation.commit_sha, branch: .invocation.branch_name}'` | Repo context |
| `GetLog` | `-r '.log'` | Full build log |
| `GetLog` | `-r '.log' \| grep -iE "(error\|fail\|fatal)" \| head -20` | Errors only |

## GitHub PR Integration

```bash
# Extract invocation IDs from failed PR checks
gh pr checks --json link,state | \
  jq -r '.[] | select(.state == "FAILURE") | .link' | \
  grep buildbuddy | \
  sed 's|.*/invocation/||'
```

Then use the invocation ID with the API request pattern above.

## Tips

- BuildBuddy logs are paginated - use page tokens for large logs
- Invocation IDs are extracted from URLs: `https://jomcgi.buildbuddy.io/invocation/<id>`
- Use jq to parse JSON responses and extract relevant fields
- The log endpoint returns a single string (not structured log entries)
- Check `.invocation.success` boolean to see if build passed

## Environment Setup

```bash
# Verify API key is set
if [ -z "$BUILDBUDDY_API_KEY" ]; then
  echo "ERROR: BUILDBUDDY_API_KEY not set"
  echo "Get your API key from: https://jomcgi.buildbuddy.io/settings/org/details"
else
  echo "API key configured ✓"
fi
```

## References

- [BuildBuddy API Documentation](https://www.buildbuddy.io/docs/enterprise-api/)
- [BuildBuddy Authentication Guide](https://www.buildbuddy.io/docs/guide-auth/)
- [BuildBuddy Quickstart](https://www.buildbuddy.io/docs/quickstart/)
