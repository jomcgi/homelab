# Observability & Alerting

The homelab has a complete observability stack (SigNoz, OTel, Linkerd) but its alerting pipeline is broken. PagerDuty notifications never fire due to a channel sync bug, 17 services lack HTTPCheck alerts, and the synthetic monitoring system has a silent failure mode where it stops producing metrics without triggering any alert. This RFC consolidates issues #458, #445, and #444 into a single plan to make alerting reliable.

## Current State

**What works:** 14 HTTPCheck endpoints are configured in the OTel deployment collector. 12 infrastructure alerts (4 node conditions, 4 ArgoCD app states, 3 pod health, 1 restart rate) and 6 HTTPCheck alerts exist as ConfigMaps synced by the signoz-dashboard-sidecar. All 23 alert rules are synced and enabled in SigNoz.

**What doesn't work:** The PagerDuty notification channel sync is stuck in a create/update conflict -- the sidecar POSTs a new channel every 5 minutes instead of PUTting the existing one, so no pages are ever delivered. An orphaned `k8s-infra-otel-deployment` pod has been failing for 100+ days. Only 6 of ~23 services have HTTPCheck alerts. If the httpcheck receiver stops collecting, alerts go inactive instead of firing.

## Failure Modes

| Failure Mode | Severity | Current Detection | Gap |
|---|---|---|---|
| PagerDuty channel sync conflict | Critical | None -- fails silently every 5 min | Sidecar lacks `getChannelByName()` to detect existing channels |
| Service goes down (no HTTPCheck alert defined) | Critical | None for 17 services | Missing alert ConfigMaps for cluster-critical and prod services |
| HTTPCheck receiver stops producing metrics | Medium | None -- alerts go `inactive` silently | No dead man's switch to detect absent metrics |
| Orphaned OTel deployment in error loop | Low | Noisy logs, wasted resources | Not pruned by ArgoCD (name prefix changed) |

## Proposed Alerting Strategy

### Infrastructure Layer (exists, working)

Node and ArgoCD alerts are already in place under `overlays/cluster-critical/signoz/alerts/`. These cover node pressure conditions (disk, memory, PID), node readiness, pod OOMKills, pod pending/restart rates, and ArgoCD application states (degraded, missing, out-of-sync, suspended). No changes needed here beyond fixing the PagerDuty delivery path.

### Application Layer (HTTPCheck gaps)

Every service exposed through Cloudflare Tunnel or Cloudflare Pages needs an HTTPCheck alert ConfigMap following the established pattern: 10-minute eval window, 2-minute frequency, 5 consecutive failures to trigger, severity critical, notification via `pagerduty-homelab`.

**Cluster-critical services needing alerts (#445):** argocd-image-updater, cert-manager, coredns, kyverno, linkerd, nvidia-gpu-operator, signoz-dashboard-sidecar.

**Production services needing alerts (#444):** cloudflare-tunnel, gh-arc-controller, gh-arc-runners, knowledge-graph, llama-cpp, nats, openclaw-friends, openclaw-personal, perplexica, seaweedfs.

Each alert should be a ConfigMap in the service's overlay directory, added to its `kustomization.yaml`.

### Synthetic Monitoring (Dead Man's Switch)

Add a meta-alert that fires when the httpcheck receiver itself stops producing data:

- **Query:** `count(httpcheck.status) == 0` over a 10-minute window
- **Condition:** If zero httpcheck data points are observed for 10 minutes, fire critical alert
- **Purpose:** Detects OTel deployment failure, Cloudflare service token expiry, or receiver misconfiguration
- **Location:** `overlays/cluster-critical/signoz/alerts/httpcheck-dead-mans-switch.yaml`

This closes the gap where the monitoring pipeline silently dies and all HTTPCheck alerts go inactive.

## Action Items

1. **Fix PagerDuty channel sync in sidecar (#458-1)** -- Add `getChannelByName()` / `listChannels()` to the sidecar's channel reconciler. On sync, query existing channels by name before attempting POST. If channel exists, use PUT with the existing ID. Handle 400 conflict errors gracefully.

2. **Delete orphaned OTel deployment (#458-2)** -- Remove stale `k8s-infra-otel-deployment` Deployment from the cluster (pre-rename artifact). Add to ArgoCD resource pruning if needed.

3. **Add dead man's switch alert (#458-3)** -- Create `httpcheck-dead-mans-switch.yaml` ConfigMap alert that fires when `count(httpcheck.status) == 0` over 10 minutes.

4. **Add 7 cluster-critical HTTPCheck alerts (#445)** -- One ConfigMap per service, following the `api-gateway-httpcheck-alert.yaml` pattern.

5. **Add 10 prod service HTTPCheck alerts (#444)** -- One ConfigMap per service, same pattern.

6. **Verify end-to-end** -- After fixes 1-5, confirm by temporarily breaking a health check endpoint and validating that a PagerDuty page is received.
