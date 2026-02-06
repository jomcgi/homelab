# Lock File Unification & BuildBuddy CF Pages Integration

## Status: Proposed

## Problem Statement

The repository currently uses a **hybrid lock file approach** that creates potential inconsistencies:

| Build System | Lock File | Used By |
|--------------|-----------|---------|
| Bazel | `/pnpm-lock.yaml` (root) | All Bazel builds, wrangler rules |
| GitHub Actions | `websites/<site>/package-lock.json` | CI workflows via `npm ci` |

This means:
- Bazel esbuild/vite builds resolve dependencies from `pnpm-lock.yaml`
- GitHub Actions CF Pages deploys resolve from local `package-lock.json` files
- These can drift apart, causing inconsistent builds between local and CI

### Current Deployment Matrix

| Site | Bazel wrangler | GitHub Actions | Build Tool |
|------|----------------|----------------|------------|
| trips.jomcgi.dev | ✅ | ✅ | Vite + esbuild |
| jomcgi.dev | ❌ | ✅ | Astro |
| hikes.jomcgi.dev | ❌ | ✅ | None (static) |
| ships.jomcgi.dev | ❌ | ❌ (container) | Vite |

### Environment Variable Inconsistency

**Resolution:** Use `CLOUDFLARE_API_TOKEN` consistently across all systems to match tooling expectations.

| System | Secret/Var Name | What Tool Expects |
|--------|-----------------|-------------------|
| GitHub Actions | `CLOUDFLARE_API_TOKEN` | `CLOUDFLARE_API_TOKEN` ✅ |
| BuildBuddy (planned) | `CLOUDFLARE_API_TOKEN` | `CLOUDFLARE_API_TOKEN` ✅ |
| Wrangler CLI | - | `CLOUDFLARE_API_TOKEN` ✅ |
| Cloudflare Operator | - | `CLOUDFLARE_API_TOKEN` ✅ |

The buildbuddy.yaml previously planned to use `CF_API_TOKEN` with translation:
```yaml
# ❌ OLD (remove this indirection)
export CLOUDFLARE_API_TOKEN="$CF_API_TOKEN"
```

This indirection is unnecessary and error-prone. BuildBuddy should inject `CLOUDFLARE_API_TOKEN` directly from organization secrets.

## Proposed Solution

Migrate all Cloudflare Pages deployments to Bazel + BuildBuddy, eliminating GitHub Actions workflows and consolidating on the shared `pnpm-lock.yaml`.

## Execution Plan

### Phase 1: Enable BuildBuddy CF Pages Deployment

**Prerequisites:**
- [ ] Add `CLOUDFLARE_API_TOKEN` secret to BuildBuddy organization settings
  - ✅ Use standard name `CLOUDFLARE_API_TOKEN` (not `CF_API_TOKEN`) to match GitHub Actions and wrangler CLI expectations

**Tasks:**
1. [ ] Update and uncomment the disabled deployment step in `buildbuddy.yaml`:
   ```yaml
   - name: "Deploy Pages"
     steps:
       - run: bazel run //websites:push_all_pages --config=ci
   ```
   ✅ No `export` translation needed - BuildBuddy injects `CLOUDFLARE_API_TOKEN` directly from secrets.

2. [ ] Remove any `CF_API_TOKEN` references in `buildbuddy.yaml` and use `CLOUDFLARE_API_TOKEN` consistently
3. [ ] Test deployment of trips.jomcgi.dev via BuildBuddy
4. [ ] Verify the deployed site matches GitHub Actions deployment

### Phase 2: Add Bazel Wrangler Rules to Remaining Sites

**jomcgi.dev (Astro):**
1. [ ] Add wrangler binary target to `websites/jomcgi.dev/BUILD`
2. [ ] Create `wrangler_pages` target for the Astro dist output
3. [ ] Add to `//websites:push_all_pages` multirun target
4. [ ] Test deployment via `bazel run //websites/jomcgi.dev:jomcgi.push`

**hikes.jomcgi.dev:**
1. [ ] Evaluate if Bazel integration makes sense (site uses container-based updates)
2. [ ] If yes, add wrangler targets similar to trips.jomcgi.dev
3. [ ] If no, document exception and keep GitHub Actions workflow

### Phase 3: Remove GitHub Actions Workflows

Once BuildBuddy deployments are verified:

1. [ ] Remove `.github/workflows/cf-pages-deploy-homepage.yaml`
2. [ ] Remove `.github/workflows/cf-pages-deploy-trips.yaml`
3. [ ] Evaluate `.github/workflows/cf-pages-deploy-hikes.yaml` (may need to keep for container-based data updates)

### Phase 4: Clean Up Local Lock Files

After GitHub Actions workflows are removed:

1. [ ] Evaluate if local `package-lock.json` files are still needed
2. [ ] If only used for IDE tooling, consider adding to `.gitignore`
3. [ ] Document the single-lock-file approach in CLAUDE.md

## Benefits

1. **Single source of truth** - All builds use `pnpm-lock.yaml`
2. **Consistent builds** - Same dependencies in local dev and CI
3. **Unified CI** - All deployments in BuildBuddy, not split between GHA and BB
4. **Reduced complexity** - No need to sync multiple lock files
5. **Consistent env vars** - `CLOUDFLARE_API_TOKEN` everywhere, no translation layers

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| BuildBuddy secret misconfiguration | Test with a single site first (trips.jomcgi.dev) |
| Astro build differences | Compare dist outputs between npm and pnpm builds |
| hikes.jomcgi.dev container workflow | May need to keep GHA workflow for data updates |

## Related Files

- `buildbuddy.yaml` - CI configuration with disabled CF deployment
- `tools/wrangler/wrangler_pages.bzl` - Bazel rule for CF Pages
- `websites/BUILD` - Multirun target for all page deployments
- `websites/trips.jomcgi.dev/BUILD` - Reference implementation

## References

- [BuildBuddy Secrets Documentation](https://www.buildbuddy.io/docs/secrets)
- [aspect_rules_js pnpm integration](https://github.com/aspect-build/rules_js)
