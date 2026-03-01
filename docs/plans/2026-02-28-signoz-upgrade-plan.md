# SigNoz Upgrade v0.92 → v0.113 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the SigNoz Helm chart from v0.92 to v0.113, preserving ClickHouse data via schema migration.

**Architecture:** Bump the wrapper chart's two dependencies (`signoz` and `k8s-infra`), regenerate vendored tarballs, commit, and let ArgoCD auto-sync. No overlay values changes needed.

**Tech Stack:** Helm, ArgoCD, SigNoz, ClickHouse, OTel Collector

---

### Task 1: Create worktree

**Step 1: Create a feature branch worktree**

```bash
git -C ~/repos/homelab worktree add -b feat/signoz-upgrade /tmp/claude-worktrees/signoz-upgrade origin/main
```

**Step 2: Verify worktree**

```bash
cd /tmp/claude-worktrees/signoz-upgrade && git log --oneline -1
```

Expected: Latest commit on main.

---

### Task 2: Bump chart dependency versions

**Files:**
- Modify: `charts/signoz/Chart.yaml`

**Step 1: Update Chart.yaml**

Edit `charts/signoz/Chart.yaml` to change:

```yaml
appVersion: "0.113.0"
dependencies:
  - name: signoz
    version: 0.113.0
    repository: https://charts.signoz.io
  - name: k8s-infra
    version: 0.15.0
    repository: https://charts.signoz.io
```

Three changes:
- `appVersion`: `"0.92.0"` → `"0.113.0"`
- `signoz` version: `0.92.0` → `0.113.0`
- `k8s-infra` version: `0.14.1` → `0.15.0`

**Step 2: Verify the edit**

```bash
grep -E 'appVersion|version:' charts/signoz/Chart.yaml
```

Expected: Shows `0.113.0` for appVersion and signoz, `0.15.0` for k8s-infra.

---

### Task 3: Update vendored chart tarballs

**Files:**
- Remove: `charts/signoz/charts/signoz-0.92.0.tgz`
- Remove: `charts/signoz/charts/k8s-infra-0.14.1.tgz`
- Create: `charts/signoz/charts/signoz-0.113.0.tgz`
- Create: `charts/signoz/charts/k8s-infra-0.15.0.tgz`
- Regenerate: `charts/signoz/Chart.lock`

**Step 1: Remove old tarballs**

```bash
rm charts/signoz/charts/signoz-0.92.0.tgz charts/signoz/charts/k8s-infra-0.14.1.tgz
```

**Step 2: Download new tarballs and regenerate lock**

```bash
cd charts/signoz && helm dependency update .
```

Expected: Downloads `signoz-0.113.0.tgz` and `k8s-infra-0.15.0.tgz`, updates `Chart.lock`.

**Step 3: Verify new tarballs**

```bash
ls charts/signoz/charts/
```

Expected: `signoz-0.113.0.tgz` and `k8s-infra-0.15.0.tgz` (no old versions).

---

### Task 4: Validate Helm template renders

**Step 1: Render templates with overlay values to check for errors**

```bash
helm template signoz charts/signoz/ -f overlays/cluster-critical/signoz/values.yaml 2>&1 | head -20
```

Expected: YAML output, no errors. If there are unknown key warnings, they're safe to ignore (Helm warns on extra values).

**Step 2: Verify the SigNoz image version in rendered output**

```bash
helm template signoz charts/signoz/ -f overlays/cluster-critical/signoz/values.yaml 2>&1 | grep 'image:.*signoz' | head -5
```

Expected: Image tags reference `v0.113.0`.

**Step 3: Verify the telemetryStoreMigrator job is present**

```bash
helm template signoz charts/signoz/ -f overlays/cluster-critical/signoz/values.yaml 2>&1 | grep 'telemetrystore-migrator' | head -3
```

Expected: At least one line showing the migrator job name.

**Step 4: Verify the OTel collector image version**

```bash
helm template signoz charts/signoz/ -f overlays/cluster-critical/signoz/values.yaml 2>&1 | grep 'signoz-otel-collector' | head -3
```

Expected: Image tag shows `v0.144.1`.

---

### Task 5: Commit and push

**Step 1: Stage changes**

```bash
git add charts/signoz/Chart.yaml charts/signoz/Chart.lock charts/signoz/charts/
```

**Step 2: Verify staged files**

```bash
git status
```

Expected: Modified `Chart.yaml`, `Chart.lock`. Deleted old tarballs, added new tarballs.

**Step 3: Commit**

```bash
git commit -m "feat: upgrade SigNoz chart from v0.92 to v0.113

Bumps signoz chart 0.92.0 -> 0.113.0 and k8s-infra 0.14.1 -> 0.15.0.
Notable changes:
- schemaMigrator replaced by telemetryStoreMigrator
- SigNoz v0.95.0 -> v0.113.0 (18 versions of improvements)
- OTel collector v0.129.5 -> v0.144.1
- ClickHouse stays at 25.5.6 (no data migration needed)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Step 4: Push and create PR**

```bash
git push -u origin feat/signoz-upgrade
```

Then create PR:
```bash
gh pr create --title "Upgrade SigNoz from v0.92 to v0.113" --body "## Summary
- Bumps signoz chart dependency 0.92.0 → 0.113.0
- Bumps k8s-infra chart dependency 0.14.1 → 0.15.0
- No overlay values changes needed
- ClickHouse version unchanged (25.5.6), schema migrations run via telemetryStoreMigrator
- Fixes MCP server list-alerts API compatibility

## Test plan
- [ ] Helm template renders without errors
- [ ] ArgoCD syncs successfully
- [ ] telemetryStoreMigrator job completes (exit 0)
- [ ] SigNoz UI accessible at signoz.jomcgi.dev
- [ ] MCP list-alerts returns data
- [ ] HTTP check alerts visible and in OK state
- [ ] Dashboards still synced by sidecar

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

### Task 6: Post-deploy verification (after ArgoCD sync)

**Step 1: Check ArgoCD sync status**

```bash
kubectl get application signoz -n argocd -o jsonpath='{.status.sync.status}'
```

Expected: `Synced`

**Step 2: Check migrator job completed**

```bash
kubectl get jobs -n signoz | grep migrator
```

Expected: Job shows `1/1` completions.

**Step 3: Verify SigNoz version**

```bash
kubectl get statefulset -n signoz signoz -o jsonpath='{.spec.template.spec.containers[0].image}'
```

Expected: `signoz/signoz:v0.113.0`

**Step 4: Verify MCP list-alerts works**

Use the SigNoz MCP tool `list-alerts` — should now return the 22 configured alerts.
