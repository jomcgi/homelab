# ADR 001: Monorepo Structure & Dotfile Housekeeping

**Author:** Joe McGinley
**Status:** Accepted
**Created:** 2026-03-07

---

## Problem

A structural audit of the homelab monorepo identified two areas for improvement: top-level directory organisation and untracked/misconfigured dotfiles. The repo has grown organically and some concerns have accumulated that are worth addressing deliberately.

---

## Proposal

Address the issues in two phases:

1. **Immediate fix:** Add `.ruff_cache/` to `.gitignore` to prevent accidental commits of local tool cache.
2. **Deferred reorganisation:** Record directory structure observations for a future dedicated refactor, rather than acting on them now given the high blast radius (Bazel targets, ArgoCD manifests, CI paths all need updating).

---

## Architecture

### Dotfile Findings

#### `.ruff_cache` not gitignored

`git check-ignore` confirmed `.ruff_cache` had no matching rule in `.gitignore`, meaning it could be accidentally staged and committed. This is a pure local tool cache with no value in version control.

**Resolution:** Added `.ruff_cache/` to `.gitignore`. Verified via `git ls-files .ruff_cache` that it had not been previously committed.

#### `.venv` and `.playwright-mcp`

Both are correctly gitignored via glob patterns (`*.venv/` and `.playwright-mcp` respectively). No action required. Note that `.venv` is somewhat redundant given Python toolchaining is managed via Bazel -- it likely exists from ad-hoc local development.

#### Other dotfiles

| Dir | Status | Notes |
| --- | ------ | ----- |
| `.git` | Keep | Obviously |
| `.github` | Keep | Actions workflows |
| `.aspect` | Keep | Aspect Bazel config, should be committed |
| `.vscode` | Keep | Shared editor settings/extensions |
| `.claude` | Keep, audit periodically | Claude Code project instructions; can accumulate stale context |

### Directory Structure Observations

The following top-level structure issues were identified. These are **not actioned in this ADR** but recorded for future reorganisation work.

#### GitOps layer is fragmented

`charts/`, `overlays/`, `clusters/`, `argo-cd/`, and `seaweedfs/templates` are all deployment concerns spread across separate top-level dirs. A single `deploy/` namespace would reduce cognitive overhead, particularly as more clusters and apps are added.

#### Bazel rules are loose at root

`rules_semgrep/`, `rules_helm/`, `rules_vitepress/`, `rules_wrangler/` could live under `bazel/rules/` alongside `tools/`, forming a coherent Bazel infrastructure namespace.

#### `semgrep_rules/` vs `rules_semgrep/` naming conflict

These are easily confused: one is YAML policies, one is Bazel machinery. Renaming to `policies/semgrep/` and `bazel/rules/semgrep/` respectively would make the distinction unambiguous.

#### `docs/` and `architecture/` overlap

Both contain reference and decision material. Merging into a single `docs/` with subdirs for ADRs, plans, and reference would simplify navigation.

#### `scripts/` contains trips-service app code

Most of `scripts/` (`publish-trip-images`, `backfill-elevation`, `detect-wildlife`) is specific to the trips application. This code arguably belongs closer to its service rather than in a top-level `scripts/` dir.

### Proposed future top-level shape

| Today | Proposed | Rationale |
| ----- | -------- | --------- |
| `services/` + `websites/` | `apps/` | Unified application namespace |
| `rules_*` + `tools/` | `bazel/` | Coherent Bazel infrastructure |
| `charts/` + `overlays/` + `clusters/` + `argo-cd/` | `deploy/` | Single GitOps namespace |
| `semgrep_rules/` | `policies/` | Distinct from Bazel rules |
| `docs/` + `architecture/` | `docs/` | Merged reference material |

```
/
├── apps/           # services/ + websites/
├── bazel/          # rules_* + tools/
├── deploy/         # charts/ + overlays/ + clusters/ + argo-cd/
├── operators/      # existing + sextant/
├── policies/       # semgrep_rules/
├── docs/           # docs/ + architecture/ merged
├── third_party/
└── poc/
```

---

## Implementation

### Phase 1: Dotfile hygiene (this ADR)

- [x] Add `.ruff_cache/` to `.gitignore`
- [x] Audit all top-level dotfiles and document status

### Phase 2: Directory reorganisation (future ADR)

- [ ] Plan path migration strategy (Bazel targets, ArgoCD manifests, CI)
- [ ] Consolidate GitOps dirs into `deploy/`
- [ ] Move Bazel rules under `bazel/rules/`
- [ ] Rename `semgrep_rules/` to `policies/semgrep/`
- [ ] Merge `docs/` and `architecture/`
- [ ] Move trips-specific scripts closer to their service
- [ ] Update all references in CLAUDE.md, contributing guides, and CI config

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Directory reorg breaks Bazel targets | High | High | Automated refactor with `buildozer`; run full `bazel test //...` before merge |
| ArgoCD apps lose sync after path changes | High | High | Update all Application manifests atomically; test with `helm template` |
| Stale references in docs/guides | Medium | Low | Grep for old paths post-migration |

---

## Open Questions

1. Should Phase 2 be a single large PR or broken into incremental moves per directory?
2. Is `apps/` the right name, or should `services/` and `websites/` remain separate given their different build toolchains (Go vs JS)?

---

## References

| Resource | Relevance |
| -------- | --------- |
| [Bazel bzlmod migration](https://bazel.build/external/migration) | Context for rules directory layout |
| `architecture/contributing.md` | Will need path updates in Phase 2 |
