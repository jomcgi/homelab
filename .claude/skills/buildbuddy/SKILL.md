---
name: buildbuddy
description: Use when debugging failed CI/CD jobs, analyzing build logs, or investigating GitHub Actions failures. Access BuildBuddy remote build execution and caching service for detailed build insights.
---

# BuildBuddy - Remote Build Execution & CI Debugging

## Authentication

The BuildBuddy API is authenticated via `BUILDBUDDY_API_KEY` environment variable, sourced from 1Password secret `claude.jomcgi.dev`.

## API Endpoints

Base URL: `https://app.buildbuddy.io/api/v1`

## Debugging Failed GitHub Actions

When a PR has failing checks, use BuildBuddy to get detailed build logs and artifacts:

```bash
# Get invocation details from a GitHub Actions run
# First, get the check run ID from GitHub
gh pr checks --json name,link,conclusion

# Extract BuildBuddy invocation ID from the check run link
# BuildBuddy links typically look like: https://app.buildbuddy.io/invocation/xxxxx

# Fetch invocation details using curl
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/invocation?invocation_id=<invocation_id>"

# Get build logs
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/log?invocation_id=<invocation_id>&attempt=1"

# Get execution details for specific targets
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/target?invocation_id=<invocation_id>"
```

## Common Use Cases

### 1. Analyze Failed Bazel Builds

```bash
# Get summary of failed targets
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/invocation?invocation_id=<id>" \
  | jq '.invocation.failed_targets'

# Get detailed error logs
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/log?invocation_id=<id>&attempt=1" \
  | jq '.log_entries[] | select(.level == "ERROR")'
```

### 2. Check Build Performance

```bash
# Get timing information
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/invocation?invocation_id=<id>" \
  | jq '.invocation.timing'

# Check cache hit rates
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/invocation?invocation_id=<id>" \
  | jq '.invocation.cache_stats'
```

### 3. Download Build Artifacts

```bash
# List available artifacts
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  "https://app.buildbuddy.io/api/v1/artifacts?invocation_id=<id>"

# Download specific artifact
curl -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
  -o artifact.tar.gz \
  "https://app.buildbuddy.io/api/v1/artifact?uri=<artifact_uri>"
```

## Integration with GitHub Actions Debugging

When debugging failed PR checks:

1. **Get check details from GitHub:**
   ```bash
   # Get all checks for current PR
   gh pr checks --json name,link,conclusion,startedAt,completedAt

   # Filter for failed checks
   gh pr checks --json name,link,conclusion | jq '.[] | select(.conclusion == "FAILURE")'
   ```

2. **Extract BuildBuddy invocation ID:**
   - Look for BuildBuddy links in the check output
   - Extract the invocation ID from the URL

3. **Fetch detailed logs from BuildBuddy:**
   ```bash
   INVOCATION_ID="<extracted_id>"

   # Get full invocation details
   curl -s -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
     "https://app.buildbuddy.io/api/v1/invocation?invocation_id=$INVOCATION_ID" \
     | jq '.'

   # Get error logs specifically
   curl -s -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
     "https://app.buildbuddy.io/api/v1/log?invocation_id=$INVOCATION_ID&attempt=1" \
     | jq '.log_entries[] | select(.level == "ERROR" or .level == "FATAL")'
   ```

## Workflow for PR Debugging

1. **Check PR status:**
   ```bash
   gh pr checks
   ```

2. **If checks are failing, get BuildBuddy invocation:**
   ```bash
   gh pr checks --json link | jq -r '.[] | .link' | grep buildbuddy
   ```

3. **Fetch detailed error information:**
   ```bash
   # Parse invocation ID from URL and fetch details
   INVOCATION_ID=$(echo $BUILDBUDDY_URL | sed 's/.*invocation\///')

   curl -s -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
     "https://app.buildbuddy.io/api/v1/invocation?invocation_id=$INVOCATION_ID" \
     | jq '.invocation | {status: .invocation_status, failed: .failed_targets, duration: .duration_millis}'
   ```

4. **Get specific error messages:**
   ```bash
   curl -s -H "Authorization: Bearer $BUILDBUDDY_API_KEY" \
     "https://app.buildbuddy.io/api/v1/log?invocation_id=$INVOCATION_ID&attempt=1" \
     | jq -r '.log_entries[] | select(.level == "ERROR") | .message'
   ```

## Tips

- BuildBuddy provides detailed timing and caching metrics for Bazel builds
- Use the API to fetch logs when GitHub Actions logs are truncated
- Check cache hit rates to identify performance issues
- Download artifacts directly for local debugging
- The invocation ID is the key to accessing all build information

## Environment Setup

Ensure `BUILDBUDDY_API_KEY` is available:
```bash
# Should be automatically set from 1Password
echo $BUILDBUDDY_API_KEY | head -c 10  # Check first 10 chars only
```

If not set, the key is stored in 1Password vault `k8s-homelab` under item `claude.jomcgi.dev` as field `buildbuddy_api_key`.