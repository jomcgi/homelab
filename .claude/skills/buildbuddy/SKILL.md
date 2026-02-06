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

Base URL: `https://app.buildbuddy.io/api/v1`

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
│  From URL: https://app.buildbuddy.io/        │
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
  https://app.buildbuddy.io/api/v1/GetInvocation

# 3. Get build logs
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
  https://app.buildbuddy.io/api/v1/GetLog
```

## Common Use Cases

### 1. Analyze Failed Bazel Builds

```bash
# Get invocation summary (success status, duration, command, patterns)
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"selector":{"invocation_id":"<id>"}}' \
  https://app.buildbuddy.io/api/v1/GetInvocation \
  | jq '{success: .invocation.success, duration_ms: .invocation.duration_millis, command: .invocation.command}'

# Get build logs (includes stdout/stderr)
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"selector":{"invocation_id":"<id>"}}' \
  https://app.buildbuddy.io/api/v1/GetLog \
  | jq -r '.log'
```

### 2. Check Build Performance

```bash
# Get timing and action count
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"selector":{"invocation_id":"<id>"}}' \
  https://app.buildbuddy.io/api/v1/GetInvocation \
  | jq '{duration_ms: .invocation.duration_millis, action_count: .invocation.action_count}'
```

### 3. Get Repository Context

```bash
# Get repo URL, commit, and branch info
curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"selector":{"invocation_id":"<id>"}}' \
  https://app.buildbuddy.io/api/v1/GetInvocation \
  | jq '{repo: .invocation.repo_url, commit: .invocation.commit_sha, branch: .invocation.branch_name}'
```

## Integration with GitHub PR Debugging

### Full Workflow

```bash
# 1. Check PR status
gh pr checks --json name,conclusion,link

# 2. Extract BuildBuddy invocation IDs from failed checks
gh pr checks --json link,conclusion | \
  jq -r '.[] | select(.conclusion == "FAILURE") | .link' | \
  grep buildbuddy | \
  sed 's|.*/invocation/||'

# 3. For each failed invocation, get details
for INVOCATION_ID in $(gh pr checks --json link,conclusion | jq -r '.[] | select(.conclusion == "FAILURE") | .link' | grep buildbuddy | sed 's|.*/invocation/||'); do
  echo "=== Invocation: $INVOCATION_ID ==="

  # Get summary
  curl -s -X POST \
    -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
    https://app.buildbuddy.io/api/v1/GetInvocation \
    | jq -r '{success: .invocation.success, command: .invocation.command, duration_ms: .invocation.duration_millis}'

  # Get logs (first 50 lines)
  curl -s -X POST \
    -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
    https://app.buildbuddy.io/api/v1/GetLog \
    | jq -r '.log' | head -50

  echo ""
done
```

### Quick Error Check

```bash
# Get logs and filter for ERROR/FAILURE patterns
INVOCATION_ID="<id>"

curl -s -X POST \
  -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"selector\":{\"invocation_id\":\"$INVOCATION_ID\"}}" \
  https://app.buildbuddy.io/api/v1/GetLog \
  | jq -r '.log' \
  | grep -i -E "(error|fail|fatal)" \
  | head -20
```

## Helper Functions

Add to your shell profile for easier debugging:

```bash
# Get BuildBuddy invocation summary
bb_summary() {
  local id="$1"
  curl -s -X POST \
    -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"selector\":{\"invocation_id\":\"$id\"}}" \
    https://app.buildbuddy.io/api/v1/GetInvocation \
    | jq '{success: .invocation.success, command: .invocation.command, duration_ms: .invocation.duration_millis, action_count: .invocation.action_count}'
}

# Get BuildBuddy logs
bb_logs() {
  local id="$1"
  curl -s -X POST \
    -H "x-buildbuddy-api-key: $BUILDBUDDY_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"selector\":{\"invocation_id\":\"$id\"}}" \
    https://app.buildbuddy.io/api/v1/GetLog \
    | jq -r '.log'
}

# Get BuildBuddy errors
bb_errors() {
  local id="$1"
  bb_logs "$id" | grep -i -E "(error|fail|fatal)" | head -30
}
```

## Tips

- BuildBuddy logs are paginated - use page tokens for large logs
- Invocation IDs are extracted from URLs: `https://app.buildbuddy.io/invocation/<id>`
- Use jq to parse JSON responses and extract relevant fields
- The log endpoint returns a single string (not structured log entries)
- Check `.invocation.success` boolean to see if build passed

## Environment Setup

```bash
# Verify API key is set
if [ -z "$BUILDBUDDY_API_KEY" ]; then
  echo "ERROR: BUILDBUDDY_API_KEY not set"
  echo "Get your API key from: https://app.buildbuddy.io/settings/org/details"
else
  echo "API key configured ✓"
fi
```

## References

- [BuildBuddy API Documentation](https://www.buildbuddy.io/docs/enterprise-api/)
- [BuildBuddy Authentication Guide](https://www.buildbuddy.io/docs/guide-auth/)
- [BuildBuddy Quickstart](https://www.buildbuddy.io/docs/quickstart/)
