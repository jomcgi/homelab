# Automatic Helm Chart Versioning via Conventional Commits

## Problem

Published Helm charts (e.g., `agent-platform`) have a static version in `Chart.yaml` that is only bumped manually. CI pushes the chart to OCI on every main merge, but always with the same version tag. The ArgoCD Image Updater watches the chart OCI artifact with `updateStrategy: digest` and writes back to `spec.sources[0].targetRevision` — but since the tag never changes, the write-back is a no-op and ArgoCD never redeploys.

This caused the agent orchestrator UI to serve a stale image missing new recipe profiles, despite the code being on main and the chart being rebuilt.

## Decision

Automatically compute the next semver version from conventional commits scoped to each chart's Bazel dependency closure. The push script computes the version, pushes the chart with the new version, and commits the updated `Chart.yaml` back to main.

## Design

### Component 1: `bazel/helm/chart-version.sh`

Standalone script that computes the next chart version.

**Input**: Chart directory path (e.g., `projects/agent_platform/chart`)

**Output**: Next semver version string to stdout (e.g., `0.9.0`)

**Algorithm**:

1. Read current version from `Chart.yaml`
2. Find the commit where the version field was last set:
   `git log -1 --format=%H -S"version: <current>" -- <chart-dir>/Chart.yaml`
3. Derive the Bazel package from the chart path and query transitive source deps:
   `bazel query "deps(//<chart-dir>:chart.package)" --output=package`
4. Map packages to directory paths
5. `git log` from the last-version-commit to HEAD, filtered to those directories
6. Skip automated commits (`argocd-image-updater`, `ci-format-bot`, `chart-version-bot`)
7. Parse conventional commit prefixes to determine bump type:
   - Any `!:` suffix (e.g., `feat!:`, `fix!:`) → **major**
   - `feat` or `feat(scope)` → **minor**
   - Everything else (`fix`, `perf`, `refactor`, `style`, `docs`, `test`, `ci`, `build`, `chore`) → **patch**
8. Apply the highest-priority bump to the current version
9. If no relevant commits → output current version (signals no bump needed)

**Edge cases**:

- First run / no version commit found → use current Chart.yaml version as-is
- `bazel query` failure → fall back to chart directory only (degraded but functional)

### Component 2: `push.sh.tpl` Changes

After resolving the chart `.tgz` path and before `helm push`:

1. Call `chart-version.sh <chart-dir>` to get `NEW_VERSION`
2. If `NEW_VERSION` equals current Chart.yaml version → push as-is (no changes detected)
3. If different:
   a. Unpack `.tgz` to temp dir
   b. Patch `version:` in `Chart.yaml`
   c. Re-package with `helm package`
   d. `helm push` the re-packaged chart
4. After successful push, commit back:
   a. `sed` the version in the source `Chart.yaml`
   b. `git commit` as `chart-version-bot`
   c. `git push origin main`

The `helm_push` Bazel rule needs a new attribute to pass the chart source directory path into the push template, so `chart-version.sh` knows which chart to version.

### Component 3: CI Skip Logic

Add `chart-version-bot` to the author-skip list in all `buildbuddy.yaml` actions, matching the existing pattern for `argocd-image-updater` and `ci-format-bot`.

### Scope

Only charts with `publish = True` are affected (currently `agent-platform` and `oci-model-cache-operator`). All other charts are unchanged.

### Bazel Changes

- `push.sh.tpl` gains a `{{CHART_DIR}}` substitution and calls `chart-version.sh`
- `helm_push` rule gains a `chart_dir` string attribute passed through to the template
- `helm_chart` macro passes the chart directory to `helm_push`
- `chart-version.sh` is added as a data dependency of `helm_push`

## Bootstrapping

Tag the current state: the first run of `chart-version.sh` for `agent-platform` will find `version: 0.8.0` in `Chart.yaml`, find the commit where it was set, and compute from there. No manual intervention needed — the existing `0.8.0` tag in the OCI registry stays valid.

## Future

If more charts gain `publish = True`, they automatically get versioning — no extra setup beyond having a `Chart.yaml` with a valid version.
