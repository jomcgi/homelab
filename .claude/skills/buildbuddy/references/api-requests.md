# BuildBuddy API Request Templates

Curl fallback for when the `bb` CLI is unavailable. All requests use the BuildBuddy gRPC-web JSON API.

## Setup

```bash
BB_URL="https://jomcgi.buildbuddy.io"
BB_API_KEY="${BUILDBUDDY_API_KEY}"
```

All requests below use `${BB_URL}`, `${BB_API_KEY}`, and `${INVOCATION_ID}`.

## GetInvocation

Get build metadata, status, and timing.

```bash
curl -s "${BB_URL}/api/v1/GetInvocation" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"lookup\":{\"invocation_id\":\"${INVOCATION_ID}\"}}" \
  | jq '{
    success: .invocation[0].success,
    command: .invocation[0].command,
    duration_usec: .invocation[0].duration_usec,
    host: .invocation[0].host,
    user: .invocation[0].user,
    commit_sha: .invocation[0].commit_sha,
    branch_name: .invocation[0].branch_name
  }'
```

## GetTarget (Failed Only)

Get targets that failed in an invocation.

```bash
curl -s "${BB_URL}/api/v1/GetTarget" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"invocation_id\":\"${INVOCATION_ID}\"}" \
  | jq '[.target[] | select(.status != 1) | {label: .label, status: .status, type: .target_type}]'
```

## GetExecution

Get action execution details for an invocation.

```bash
curl -s "${BB_URL}/api/v1/GetExecution" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"invocation_id\":\"${INVOCATION_ID}\"}" \
  | jq '[.execution[] | {
    action_mnemonic: .action_mnemonic,
    target_label: .target_label,
    status: .status.code,
    worker: .executed_action_metadata.worker,
    wall_time_usec: .executed_action_metadata.usage_stats.wall_time_usec
  }]'
```

## GetCacheScoreCard

Get cache hit/miss statistics for an invocation.

```bash
curl -s "${BB_URL}/api/v1/GetCacheScoreCard" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"invocation_id\":\"${INVOCATION_ID}\"}" \
  | jq '{
    total_actions: .results | length,
    cache_hits: [.results[] | select(.action_cache_status == 1)] | length,
    cache_misses: [.results[] | select(.action_cache_status != 1)] | length
  }'
```

## GetLog (Paginated)

Get build logs. Logs may span multiple pages — use `next_page_token` to continue.

```bash
# First page
curl -s "${BB_URL}/api/v1/GetLog" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"invocation_id\":\"${INVOCATION_ID}\"}" \
  | jq '{log: .log, next_page_token: .next_page_token}'

# Subsequent pages (replace ${PAGE_TOKEN})
curl -s "${BB_URL}/api/v1/GetLog" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d "{\"invocation_id\":\"${INVOCATION_ID}\",\"page_token\":\"${PAGE_TOKEN}\"}" \
  | jq '{log: .log, next_page_token: .next_page_token}'
```

When `next_page_token` is empty or absent, all log content has been retrieved.
