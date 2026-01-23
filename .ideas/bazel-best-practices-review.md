# Bazel Best Practices Review

**Date**: 2026-01-23
**Status**: Proposal
**Author**: Claude (Bazel review session)

## Overview

Comprehensive review of our Bazel setup ahead of making this repository public. The goal is to ensure clean interfaces, simple development flows, efficient CI/pre-commit checks, and reusable rules.

## Current State Assessment: A- (Excellent)

This is a professionally-engineered, production-quality Bazel monorepo demonstrating deep expertise in modern build systems. It's well-suited for public release with minor improvements.

---

## CI/CD Context (Important)

**Our CI is NOT GitHub Actions** - it's handled by BuildBuddy Workflows via `buildbuddy.yaml`.

### Why BuildBuddy Workflows?

BuildBuddy uses **Firecracker microVMs** that preserve the Bazel target analysis cache between runs. This gives us:

- **~30 second build/test/deploy times** on PRs and pushes
- **Automatic cache restoration** - no slow cold starts
- **Remote execution** on 80 cores when needed
- **Integrated BES** (Build Event Service) for observability

### Current CI Pipeline (`buildbuddy.yaml`)

```yaml
actions:
  - name: "Test and push"
    container_image: "ubuntu-24.04"
    triggers:
      push: { branches: [main] }
      pull_request: { branches: ["*"] }
    steps:
      - run: bazel test //... --config=ci
      - run: |
          # Only push images on main branch
          if [ "${branch}" = "main" ]; then
            bazel run //images:push_all --config=ci
          fi
```

This is superior to GitHub Actions because:
1. **Preserved analysis cache** - Firecracker VMs restore Bazel's analysis cache
2. **No cache upload/download overhead** - Cache is local to the VM
3. **Consistent environments** - Same Ubuntu 24.04 image every time
4. **Integrated remote execution** - Falls back to RBE when needed

---

## Key Strengths

### 1. Modern Bazel Configuration
- **Fully migrated to bzlmod** - no legacy WORKSPACE file
- **44 direct dependencies** explicitly declared with `bazel_dep()`
- **Well-documented .bazelrc** with explanatory comments on every setting
- **BuildBuddy RBE** with 80-core remote execution and intelligent caching

### 2. Custom Rules Quality
- **OCI image macros** (`go_image`, `py3_image`, `apko_image`) are well-designed and reusable
- **Multi-platform support** (amd64/arm64) built into all image rules
- **Excellent docstrings** with examples in most macros
- **Stamped builds** with conditional CI/local tagging

### 3. Developer Experience
- **Unified `format` command** runs all formatters in parallel
- **Hermetic tooling** - no system dependencies via `bazel_env`
- **VS Code integration** with Buildifier, Starpls language server
- **Pre-commit hook** enforces GitOps workflow (prevents direct main commits)

### 4. Multi-Language Support
| Language | Tooling | Version | Status |
|----------|---------|---------|--------|
| Go | rules_go + Gazelle | 0.59.0 | Excellent |
| Python | rules_python + pip_compile | 3.13 | Excellent |
| JavaScript | aspect_rules_js | Latest | Good |
| Rust | rules_rust | Latest | Good |
| Helm/K8s | Custom Gazelle extension | N/A | Excellent |

---

## Issues & Recommendations

### High Priority (Before Public Release)

#### 1. Pre-commit Hooks Underutilized
**Current State**: Only `protect-main-branch` hook exists
**Impact**: Developers can commit without formatting/linting
**Recommendation**: Add format validation hook

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: format-check
      name: Check formatting
      entry: bash -c 'bazel build //tools/format:format_check 2>/dev/null || echo "Run format command"'
      language: system
      pass_filenames: false
```

**Note**: Full formatting in pre-commit is slow. Consider a lightweight check that validates manifests are fresh.

#### 2. No Kubernetes Manifest Validation
**Current State**: Validates manifest freshness, not schema correctness
**Impact**: Invalid manifests can pass CI and fail at deploy time
**Recommendation**: Add kubeconform validation

```bash
# Add to CI or pre-commit
kubeconform --summary --strict overlays/*/manifests/all.yaml
```

Could be added as a Bazel test target:
```python
sh_test(
    name = "validate_manifests",
    srcs = ["validate-manifests.sh"],
    data = glob(["overlays/*/manifests/all.yaml"]),
    tags = ["manual"],  # Run explicitly
)
```

#### 3. Missing Documentation for BuildBuddy CI
**Current State**: `buildbuddy.yaml` exists but not documented in CLAUDE.md
**Impact**: Contributors won't understand why we don't use GitHub Actions
**Recommendation**: Add section to CLAUDE.md explaining BuildBuddy workflow

```markdown
### CI/CD with BuildBuddy Workflows

Our CI runs on BuildBuddy Workflows (`buildbuddy.yaml`), not GitHub Actions.
BuildBuddy uses Firecracker microVMs that preserve Bazel's analysis cache,
giving us ~30 second build/test/deploy times vs minutes with cold cache.
```

#### 4. Minor Typo in tools/BUILD
**Location**: `tools/BUILD` line 74
**Issue**: `sh_binary(name = "workspace_statu",` → missing "s"
**Fix**: Rename to `workspace_status`

### Medium Priority (Polish)

#### 5. Sequential Format Pipeline
**Current State**: `multirun` uses `jobs = 10` (effectively sequential for most runs)
**Impact**: Format takes longer than needed
**Fix**: Change to `jobs = 0` for unlimited parallelism

```diff
# tools/format/BUILD
multirun(
    name = "format",
    commands = [...],
-   jobs = 10,
+   jobs = 0,  # Unlimited parallelism
)
```

#### 6. Test Coverage Gaps
**Current State**: Good test patterns exist but limited coverage
**Missing Tests**:
- Production services (hikes, marine, stargazer) lack `py_test` targets
- No integration tests for Helm chart rendering

**Recommendation**: Add test targets to production services

#### 7. Test Tags Standardization
**Current State**: Only `manual` and `no-remote` tags used
**Recommendation**: Add `size` tags for timeout management

```python
go_test(
    name = "unit_test",
    size = "small",  # 1 minute timeout
    ...
)

go_test(
    name = "integration_test",
    size = "medium",  # 5 minute timeout
    tags = ["requires-network"],
    ...
)
```

### Low Priority (Nice-to-Have)

#### 8. Container CVE Scanning
Add Trivy integration for image vulnerability scanning:
```yaml
# buildbuddy.yaml addition
- run: |
    trivy image ghcr.io/jomcgi/homelab/charts/claude:latest
```

#### 9. IDE Support Documentation
- Only VS Code configured
- Add JetBrains/IntelliJ setup instructions
- Consider Neovim configuration

#### 10. Pin Bazel Version
**Current**: `.bazelversion` set to `rolling` (Bazel 9 pre-release)
**Recommendation**: Consider pinning to `8.x` when Bazel 9 reaches GA for stability

---

## File Quality Summary

| Category | Quality | Key Files |
|----------|---------|-----------|
| Core Config | ★★★★★ | `MODULE.bazel`, `.bazelrc`, `tools/preset.bazelrc` |
| Custom Rules | ★★★★½ | `tools/oci/*.bzl`, `tools/argocd/defs.bzl` |
| CI/CD | ★★★★ | `buildbuddy.yaml` (excellent), `.pre-commit-config.yaml` (minimal) |
| Python | ★★★★★ | `requirements/BUILD`, `tools/pytest/defs.bzl` |
| Go | ★★★★★ | `go.mod`, `operators/*/BUILD` |
| Helm/K8s | ★★★★ | `tools/argocd/`, `overlays/*/BUILD` |
| Tests | ★★★★ | Good patterns, needs expansion |
| Dev Workflow | ★★★★★ | `tools/format/BUILD`, `.envrc`, `.vscode/` |

---

## Implementation Plan

### Phase 1: Documentation (This PR)
- [x] Create this review document in `.ideas/`
- [ ] Update CLAUDE.md with BuildBuddy CI context

### Phase 2: Quick Fixes
- [ ] Fix `workspace_statu` typo
- [ ] Change format `jobs = 10` to `jobs = 0`

### Phase 3: Validation Improvements
- [ ] Add kubeconform manifest validation
- [ ] Add format freshness check to pre-commit
- [ ] Standardize test size tags

### Phase 4: Test Coverage
- [ ] Add `py_test` to production services
- [ ] Add Helm chart rendering integration tests

---

## Appendix: Key Configuration Files

```
MODULE.bazel              # Bzlmod dependency management
.bazelrc                  # Build flags and configs
.bazelrc.remote           # BuildBuddy RBE configuration
tools/preset.bazelrc      # Generated best practices (210 lines)
buildbuddy.yaml           # CI workflow definition
tools/format/BUILD        # Unified format command
tools/lint/linters.bzl    # Lint aspect definitions
tools/oci/*.bzl           # OCI image macros
tools/argocd/defs.bzl     # Helm rendering rules
.pre-commit-config.yaml   # Git hooks
.envrc                    # Direnv/PATH setup
```

## Appendix: BuildBuddy vs GitHub Actions

| Aspect | BuildBuddy Workflows | GitHub Actions |
|--------|---------------------|----------------|
| Cache Strategy | Firecracker VM with preserved cache | Upload/download cache artifacts |
| Cold Start | ~30s (cache preserved) | 2-5 minutes (cache restore) |
| Remote Execution | Native 80-core RBE | Not available |
| Analysis Cache | Preserved between runs | Lost between runs |
| Build Observability | Integrated BES UI | Requires setup |
| Cost | Included with BuildBuddy | GitHub compute minutes |

The Firecracker microVM approach means our CI never starts "cold" - the analysis cache from the previous run is already there, making incremental builds extremely fast.
