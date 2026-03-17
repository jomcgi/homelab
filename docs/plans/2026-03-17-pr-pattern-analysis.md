# PR Pattern Analysis: Static Rules & Hooks Opportunities

**Date:** 2026-03-17
**Commit range:** Recent merged PRs on main

## Merged PRs Analyzed

| PR | Title | Pattern |
|----|-------|---------|
| #1205 | fix(context-forge): remove admin email from chart defaults | Hardcoded config value shadowing 1Password secret |
| #1206 | fix(coredns): correct YAML structure in application.yaml | retry block misplaced outside syncPolicy |
| #1207 | fix(platform): correct retry indentation in longhorn and nvidia-gpu-operator | Same retry misplacement in 2 more files |

Test-only PRs (#1211-#1238) reviewed - clean unit test additions, no anti-patterns.

## Pattern 1: Hardcoded Config Values Shadowing Secrets (PR #1205)

PLATFORM_ADMIN_EMAIL was hardcoded in chart values.yaml config block. The same key was provided by a 1Password secret via extraEnvFrom. In K8s, explicit env entries take precedence over envFrom, so the stale value silently won - causing auth failures.

**Proposed rule: no-hardcoded-email-in-config** (semgrep, YAML)
- Detect hardcoded email addresses in Helm values config/env blocks
- Emails are PII and should come from secrets
- Severity: WARNING
- Current state: No remaining violations

## Pattern 2: ArgoCD retry Block Misplaced (PR #1206, #1207)

The retry block appeared at the wrong YAML level - as a sibling of syncPolicy at the spec level, or mangled under ignoreDifferences. Correct location is spec.syncPolicy.retry.

**Proposed rule: argocd-retry-under-spec** (semgrep, YAML)
- Detect retry appearing as a direct child of spec in ArgoCD Application manifests
- Severity: ERROR
- Current state: All 28 files now correct

## Pattern 3: Chart Version Sync Hook

PR #1207 included Chart.yaml version bump alongside application.yaml targetRevision update. No preventive check exists during authoring.

**Proposed hook: check-chart-version-sync** (Claude PreToolUse, Write|Edit)
- When editing Chart.yaml version, warn if application.yaml targetRevision not updated
- Complements existing chart-version-bot

## Pipeline

1. **research** - Validate rule designs, confirm zero false positives
2. **code-fix** - Implement all three changes as separate PRs, auto-merged
3. **critic** - Validate implementations for correctness
