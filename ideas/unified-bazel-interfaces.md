# Unified Bazel Interfaces Proposal

> **Status:** Proposal
> **Created:** 2026-01-21
> **Author:** Claude Code

## Goal

Create "one way to do anything" via Bazel - simple, consistent interfaces optimized for LLM workflows.

## Current State Summary

### Existing Skills (8 total)

| Skill      | Mechanism              | Bazel-ified?     |
| ---------- | ---------------------- | ---------------- |
| bazelisk   | `bazel run/build/test` | Yes              |
| gh-pr      | `gh` CLI               | No (appropriate) |
| helm       | `helm template/lint`   | **Redundant**    |
| kubectl    | `kubectl get/logs`     | No               |
| signoz     | MCP tools              | No (appropriate) |
| buildbuddy | curl API               | No               |
| worktree   | `git worktree`         | No (appropriate) |

### Key Redundancies Found

1. **Helm rendering**: `helm template` (skill) vs `bazel run //.../render_manifests` vs `format`
2. **Manifest inspection**: Manual paths vs no discovery mechanism
3. **Cluster inspection**: Raw kubectl, not wrapped or discoverable

### What Works Well

- `format` command - single entry point for formatting + rendering
- Custom Bazel macros (apko_image, go_image, py3_image) - deep modules with simple interfaces
- ArgoCD Gazelle extension - auto-generates BUILD files
- bazel_env provides hermetic tool access

---

## Recommendations

### 1. Deprecate `helm` Skill (Merge into bazelisk)

**Why:** helm skill documents raw CLI commands that are already covered by Bazel:

- `helm template` → `bazel run //overlays/<env>/<svc>:render_manifests`
- `helm lint` → Should add `bazel run //charts/<svc>:lint`
- Rendering all → `format`

**Action:**

- Add `:lint` target generation to ArgoCD Gazelle extension
- Update bazelisk skill to document chart operations
- Archive helm skill (keep for reference, mark deprecated)

### 2. Add Cluster Inspection Targets

Create `//tools/cluster/BUILD` with read-only kubectl wrappers:

```
//tools/cluster:pods       → kubectl get pods -A (summary)
//tools/cluster:events     → kubectl get events --sort-by='.lastTimestamp'
//tools/cluster:status     → cluster health summary (nodes, storage, critical pods)
//tools/cluster:argocd     → ArgoCD app sync status
```

**Why:** Makes discovery easier. LLM can `bazel query //tools/cluster/...` to see available operations.

### 3. Add Per-Service Inspection Targets

Extend ArgoCD Gazelle to generate per-service targets:

```
//overlays/dev/claude:status   → pods, events, ArgoCD sync for this service
//overlays/dev/claude:logs     → aggregate logs for this service
//overlays/dev/claude:diff     → ArgoCD live vs rendered diff
```

**Why:** Service-specific operations without remembering namespaces/selectors.

### 4. Add Discovery Target

Create `//tools:help` that lists all available targets with descriptions:

```bash
$ bazel run //tools:help

HOMELAB BAZEL TARGETS
=====================

FORMATTING & BUILDS:
  format                                    Format code + render all manifests
  bazel build //...                         Build all targets
  bazel test //...                          Run all tests

CLUSTER INSPECTION (read-only):
  bazel run //tools/cluster:pods            List all pods
  bazel run //tools/cluster:status          Cluster health summary
  bazel run //tools/cluster:argocd          ArgoCD sync status

SERVICE OPERATIONS:
  bazel run //overlays/<env>/<svc>:render_manifests   Render Helm manifests
  bazel run //overlays/<env>/<svc>:status             Service status
  bazel run //overlays/<env>/<svc>:logs               Service logs
  bazel run //charts/<svc>:lint                       Lint Helm chart

IMAGES:
  bazel run //images:push_all               Push all container images
  bazel run //charts/<svc>/image:push       Push specific image
```

**Why:** Self-documenting system. LLMs can discover capabilities without reading docs.

### 5. Update Skills to Reference Bazel Targets

**kubectl skill** - Change from documenting raw commands to:

```markdown
## Quick Reference

bazel run //tools/cluster:pods # List all pods
bazel run //tools/cluster:status # Cluster health
bazel run //overlays/dev/claude:logs # Service logs

## Raw kubectl (when Bazel targets insufficient)

kubectl get pods -n <namespace>
...
```

**bazelisk skill** - Expand with:

- Chart linting: `bazel run //charts/<svc>:lint`
- Service inspection: `bazel run //overlays/<env>/<svc>:status`
- Discovery: `bazel run //tools:help`

---

## Implementation Plan

### Phase 1: Core Infrastructure

1. Create `tools/cluster/BUILD` with cluster inspection targets
2. Create `tools/cluster/scripts/` with wrapper scripts
3. Create `tools/help.sh` discovery script
4. Add `//tools:help` target to `tools/BUILD`

### Phase 2: Gazelle Extension

5. Extend `tools/argocd/generate.go` to generate:
   - `:lint` for each chart
   - `:status`, `:logs`, `:diff` for each overlay
6. Run `bazel run //:gazelle` to regenerate BUILD files

### Phase 3: Skill Updates

7. Update `.claude/skills/bazelisk/SKILL.md` with new targets
8. Update `.claude/skills/kubectl/SKILL.md` to reference Bazel targets
9. Deprecate `.claude/skills/helm/SKILL.md` (add deprecation notice, point to bazelisk)
10. Update `.claude/CLAUDE.md` common tasks section

### Phase 4: Simplify buildbuddy Skill

11. Create `tools/debug/fetch-ci-logs.sh` for BuildBuddy log fetching
12. Add `//tools/debug:ci_logs` target
13. Simplify buildbuddy skill to reference the Bazel target

---

## Files to Create

```
tools/cluster/
  BUILD                     # Cluster inspection targets
  scripts/
    pods.sh                 # kubectl get pods wrapper
    status.sh               # cluster health check
    events.sh               # recent events
    argocd-status.sh        # ArgoCD sync overview
    service-status.sh       # per-service status
    service-logs.sh         # per-service logs

tools/help.sh               # Discovery script

tools/debug/
  BUILD                     # Debug helper targets
  fetch-ci-logs.sh          # BuildBuddy log fetcher
```

## Files to Modify

```
tools/BUILD                           # Add :help target
tools/argocd/generate.go              # Add :lint, :status, :logs generation
.claude/skills/bazelisk/SKILL.md      # Expand with new targets
.claude/skills/kubectl/SKILL.md       # Reference Bazel targets first
.claude/skills/helm/SKILL.md          # Deprecation notice
.claude/skills/buildbuddy/SKILL.md    # Simplify to Bazel target
.claude/CLAUDE.md                     # Update common tasks
```

---

## Verification

1. Run `bazel run //tools:help` - should show all available targets
2. Run `bazel run //tools/cluster:status` - should show cluster health
3. Run `bazel run //overlays/dev/claude:status` - should show Claude service status
4. Run `bazel run //charts/claude:lint` - should lint the chart
5. Run `bazel query //tools/cluster/...` - should list all cluster targets
6. Run `bazel query //overlays/dev/claude:*` - should include status, logs, diff targets

---

## Best Practices Applied (from research)

**From [Addy Osmani's LLM Workflow](https://addyosmani.com/blog/ai-coding-workflow/):**

- Small, focused operations that fit in context
- Strong automation keeps AI honest

**From [CLI-Based LLMs Trend](https://medium.com/@saiteja.adapala/the-rise-of-cli-based-llms-why-the-terminal-is-becoming-ais-most-powerful-interface-e94099bfec3c):**

- CLI is fast, programmable, frictionless
- Easy to script and combine with other tools
- Plugs directly into build pipelines

**Applied to this repo:**

- `bazel run //...` as universal pattern
- Discovery via `//tools:help`
- Self-documenting target names
- Composable operations

---

## Design Decisions

1. **Namespace handling:** Auto-detect from application.yaml at build time (zero-config for Claude)
2. **Log output:** Last 100 lines by default (quick snapshot, doesn't block)
3. **Help format:** Plain text default, `--json` flag available for machine parsing

---

## Open Questions

1. Should we generate `:shell` targets for interactive debugging (kubectl exec into pods)?
2. How should we handle multi-replica services for logs (aggregate vs pick one)?
3. Should `//tools:help` be auto-generated from BUILD file metadata or manually curated?

---

## Next Steps

After this proposal is reviewed and approved:

1. Create implementation PR for Phase 1 (core infrastructure)
2. Iterate based on feedback
3. Continue with Phases 2-4
