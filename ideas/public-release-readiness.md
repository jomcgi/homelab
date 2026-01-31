# Public Release Readiness Plan

This document outlines changes needed before making the homelab repository public, focusing on **intuitive repo structure** and **reusability**. Sensitive data review is handled separately.

## Executive Summary

The codebase is **well-architected with strong engineering fundamentals**, but needs **documentation polish** before public release. The main gaps are around discoverability, not code quality.

---

## Critical Issues (Must Fix)

### 1. Missing Main README.md

No top-level README exists. New users land on a blank page with no orientation.

**Fix:** Create a 500-1000 word README with:

- Project purpose and philosophy
- Architecture overview (adapt from CLAUDE.md)
- Quick start link
- Directory structure summary

### 2. Orphaned Overlay Directories

These create confusion and clutter:

```
overlays/cluster-critical/envoy/
overlays/dev/fizzy/
overlays/dev/freshrss/
overlays/dev/n8n-obsidian-api/
overlays/dev/ttyd-session-manager/
overlays/prod/n8n/
```

**Fix:** Remove these directories or document why they exist.

### 3. Helm Charts Lack README Files

Only `charts/coredns/README.md` exists - excellent model but singular. 22 other charts have no documentation.

**Fix:** Add README to each chart explaining:

- What it does
- Key configuration options
- Troubleshooting tips

### 4. Services/Websites Missing Documentation

| Component                 | README  | Notes                                     |
| ------------------------- | ------- | ----------------------------------------- |
| services/hikes            | Missing | Complex scraper with multiple components  |
| services/ais_ingest       | Missing | Clean code, needs usage docs              |
| services/ships_api        | Missing | WebSocket + NATS integration undocumented |
| services/trips_api        | Missing | No API schema documentation               |
| websites/ships.jomcgi.dev | Missing | React app with no build instructions      |
| services/stargazer        | Present | Excellent - use as template for others    |

---

## Medium Priority Issues

### 5. Inconsistent Patterns Across Overlays

- **Path notation**: Some use `./application.yaml`, others use `application.yaml`
- **repoURL**: Some have `.git` suffix, some don't
- **syncOptions**: `ServerSideApply` applied inconsistently across services
- **Missing headers**: `dev/kustomization.yaml` lacks apiVersion/kind

**Fix:** Standardize all Application specs and kustomization files.

### 6. Helm Chart Code Duplication

All 20+ charts copy identical `_helpers.tpl` templates (~95% identical code). Not blocking for public release, but creates maintenance burden.

**Fix (future):** Consider extracting shared helpers or documenting the pattern.

### 7. Cloudflare Operator Needs Documentation

Code quality is excellent (circuit breakers, rate limiting, state machines), but:

- No getting-started guide for users
- Incomplete sample CRDs in `config/samples/`
- TODOs scattered throughout code

**Fix:** Add deployment guide and complete the sample configurations.

### 8. CI/CD Workflow Gaps

- No `CONTRIBUTING.md` or workflow documentation
- Self-hosted runners (`homelab-runners`) not explained to external contributors
- 7 secrets referenced in workflows without documentation
- Hard-coded values: `ghcr.io/jomcgi/homelab`, bucket names

**Fix:** Create workflow documentation and secrets guide.

### 9. Build File Typo

`tools/BUILD` line 74: `workspace_statu` should be `workspace_status`

---

## What's Already Good

| Area               | Status    | Notes                                             |
| ------------------ | --------- | ------------------------------------------------- |
| Architecture       | Excellent | Clear separation: charts/ → overlays/ → clusters/ |
| Security practices | Excellent | Non-root, read-only FS, proper securityContext    |
| CLAUDE.md          | Excellent | Comprehensive internal docs                       |
| Naming conventions | Good      | Consistent kebab-case throughout                  |
| Error handling     | Excellent | Cloudflare operator has production-grade patterns |
| Observability      | Excellent | Automatic OTEL + Linkerd injection via Kyverno    |
| Bazel docs         | Good      | README.bazel.md is solid                          |
| Stargazer service  | Excellent | Use as documentation template                     |

---

## Recommended Action Plan

### Phase 1: Documentation (Before Public Release)

1. [ ] Create `/README.md` - project overview and quick start
2. [ ] Create `/CONTRIBUTING.md` - development workflow for contributors
3. [ ] Create `/docs/ADDING_NEW_SERVICE.md` - template for adding services
4. [ ] Add README to top 10 most important charts:
   - [ ] argocd
   - [ ] linkerd
   - [ ] cert-manager
   - [ ] kyverno
   - [ ] longhorn
   - [ ] signoz
   - [ ] cloudflare-tunnel
   - [ ] marine
   - [ ] claude
   - [ ] api-gateway

### Phase 2: Cleanup

5. [ ] Remove 6 orphaned overlay directories
6. [ ] Fix `dev/kustomization.yaml` - add apiVersion/kind headers
7. [ ] Standardize Application specs:
   - [ ] Consistent repoURL format (always use `.git` suffix)
   - [ ] Consistent syncOptions across services
   - [ ] Consistent path notation in kustomization files
8. [ ] Fix typo in `tools/BUILD` (workspace_statu → workspace_status)

### Phase 3: Service Documentation

9. [ ] Add README to each service (use stargazer as template):
   - [ ] services/hikes
   - [ ] services/ais_ingest
   - [ ] services/ships_api
   - [ ] services/trips_api
10. [ ] Document API schemas for ships-api and trips-api
11. [ ] Add .env.example files for local development

### Phase 4: Nice-to-Have (Post-Release)

12. [ ] Document GitHub Actions workflows in `WORKFLOWS.md`
13. [ ] Create secrets documentation for CI setup
14. [ ] Consolidate Helm chart `_helpers.tpl` templates
15. [ ] Add chart-level README to cloudflare operator helm chart
16. [ ] Complete cloudflare operator sample CRDs

---

## Detailed Findings by Area

### Repository Structure

The three-tier organization is intuitive:

- **cluster-critical/**: Core infrastructure (argocd, cert-manager, linkerd, longhorn, signoz)
- **prod/**: Production services (cloudflare-tunnel, trips, nats, seaweedfs, vllm)
- **dev/**: Development/experimental services (marine, claude, cloudflare-operator, stargazer)

**Issue:** Steering documents in `.claude/steering/structure.md` reference outdated structure (mentions `overlays/base/` which doesn't exist).

### Helm Charts

**Strengths:**

- All charts follow standard Helm 3 structure
- Consistent naming conventions for helpers
- Good parameterization for different environments

**Issues:**

- 95% code duplication in `_helpers.tpl` across charts
- Inconsistent component label handling (some in helpers, some inline)
- Four charts have `readOnlyRootFilesystem: false` with TODOs to fix

### Overlays/Kustomize

**Strengths:**

- Minimal duplication in values.yaml files (correctly defers to chart defaults)
- Clear ArgoCD Application pattern

**Issues:**

- `namePrefix: prod-` in prod/kustomization.yaml conflicts with explicit prefixes in Application names
- Inconsistent `ignoreMissingValueFiles` usage
- Inconsistent retry configuration (only cluster-critical services have it)

### Cloudflare Operator

**Strengths:**

- Production-grade error handling (circuit breakers, rate limiting)
- Clean state machine implementation via Sextant
- Excellent OpenTelemetry tracing throughout

**Issues:**

- Missing getting-started documentation
- Chart version 0.2.0 (should be 1.0.0 for public release)
- `appVersion: latest` should be pinned

### Services and Websites

**Strengths:**

- High Python code quality with type hints
- Consistent async/await patterns
- Good database patterns (batch inserts, indexing)

**Issues:**

- Mixed logging patterns in hikes service (`print()` vs `logger`)
- No standalone Docker build instructions (relies entirely on Bazel)
- No docker-compose.yml for local multi-service testing

### CI/CD and Build System

**Strengths:**

- Well-commented `.bazelrc` files
- Good README.bazel.md technical reference
- BuildBuddy integration for remote caching

**Issues:**

- Steep learning curve with no "Getting Started" guide
- Multiple `.bazelrc` files with unclear usage
- Complex workspace_status.sh with undocumented CI detection logic

---

## Conclusion

The repository demonstrates excellent engineering practices and is fundamentally sound. The primary work needed for public release is **documentation and cleanup**, not code changes. Following the phased action plan above will make the repository accessible to external contributors while maintaining the high quality standards already established.
