# SigNoz Upgrade: v0.92 to v0.113

## Context

SigNoz is 18 versions behind latest (deployed v0.95.0, chart pinned to 0.92.0).
The SigNoz MCP server (`v0.0.5`, latest available) cannot list alerts — likely due to API
incompatibility with the older SigNoz version. Historical data is not critical, but
API keys and alert configurations stored in ClickHouse should be preserved via schema migration.

## Decision

Bump chart dependencies in-place and let ArgoCD auto-sync. Keep the ClickHouse PVC
so that the `telemetryStoreMigrator` runs schema migrations, preserving API keys
and existing SigNoz state.

## Changes

### 1. `charts/signoz/Chart.yaml`

Update dependencies:

| Dependency | Current | Target |
|------------|---------|--------|
| `signoz` | 0.92.0 | 0.113.0 |
| `k8s-infra` | 0.14.1 | 0.15.0 |
| `appVersion` | 0.92.0 | 0.113.0 |

### 2. `charts/signoz/charts/`

Replace vendored tarballs via `helm dependency update`:

- Remove `signoz-0.92.0.tgz`, `k8s-infra-0.14.1.tgz`
- Add `signoz-0.113.0.tgz`, `k8s-infra-0.15.0.tgz`
- Regenerate `Chart.lock`

### 3. `overlays/cluster-critical/signoz/values.yaml`

No changes required:

- No `schemaMigrator` overrides exist (the 0.113 breaking rename to
  `telemetryStoreMigrator` is handled by chart defaults)
- ClickHouse version unchanged (`25.5.6`) across both chart versions
- OTel collector config structure unchanged in k8s-infra 0.15.0
- httpcheck receivers and Prometheus scraping config are OTel-level, unaffected

### Unchanged

- 22 alert ConfigMaps (httpcheck + metric alerts)
- Dashboard sidecar (independent chart)
- MCP server (independent deployment)

## Rollout

ArgoCD auto-syncs with `selfHeal: true`. Pushing the chart update will:

1. Run `telemetryStoreMigrator` job (bootstrap + sync + async schema migrations)
2. Roll SigNoz StatefulSet (`v0.95.0` -> `v0.113.0`)
3. Roll OTel collector (`v0.129.5` -> `v0.144.1`)
4. ClickHouse stays at `25.5.6` — no restart needed

## Rollback

Revert the commit. ArgoCD syncs back to 0.92.0.

## Expected outcome

- MCP `list-alerts` returns data (API compatibility restored)
- 18 versions of SigNoz improvements
- OTel collector v0.129.5 -> v0.144.1
- API keys and alert rules preserved via schema migration
