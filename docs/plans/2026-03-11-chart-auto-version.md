# Automatic Helm Chart Versioning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically compute and bump Helm chart versions from conventional commits scoped to each chart's Bazel dependency closure, so the ArgoCD Image Updater detects new chart versions and triggers redeployments.

**Architecture:** A standalone `chart-version.sh` script computes the next semver version by querying Bazel deps and parsing git history. The `push.sh.tpl` calls it before pushing, re-packages the chart with the new version, and commits the updated `Chart.yaml` back to main.

**Tech Stack:** Bash, Bazel query, git, Helm CLI, Starlark (Bazel rules)

---

### Task 1: Create `chart-version.sh`

**Files:**

- Create: `bazel/helm/chart-version.sh`

**Step 1: Create the script with version computation logic**

```bash
#!/usr/bin/env bash
# Compute the next semver version for a Helm chart based on conventional commits
# scoped to the chart's Bazel dependency closure.
#
# Usage: chart-version.sh <chart-dir> [--bazel-package <label>]
# Output: Next semver version to stdout (e.g., "0.9.0")
#         Outputs current version if no bump needed.
#
# Requires: git, bazel (optional — falls back to chart-dir-only scoping)
set -o errexit -o nounset -o pipefail

CHART_DIR="${1:?Usage: chart-version.sh <chart-dir>}"
BAZEL_PACKAGE="${2:-}"

# --- Read current version from Chart.yaml ---
CHART_YAML="${CHART_DIR}/Chart.yaml"
if [[ ! -f "$CHART_YAML" ]]; then
  echo >&2 "ERROR: Chart.yaml not found at $CHART_YAML"
  exit 1
fi

CURRENT_VERSION=$(grep '^version:' "$CHART_YAML" | head -1 | awk '{print $2}' | tr -d '"')
if [[ -z "$CURRENT_VERSION" ]]; then
  echo >&2 "ERROR: Could not parse version from $CHART_YAML"
  exit 1
fi

# --- Find the commit where this version was last set ---
VERSION_COMMIT=$(git log -1 --format=%H -S"version: ${CURRENT_VERSION}" -- "$CHART_YAML" 2>/dev/null || true)
if [[ -z "$VERSION_COMMIT" ]]; then
  # No previous version commit found (first run or initial version)
  echo >&2 "INFO: No previous version commit found for ${CURRENT_VERSION}, returning current version"
  echo "$CURRENT_VERSION"
  exit 0
fi

# --- Determine dependency directories ---
DEP_DIRS=""
if [[ -n "$BAZEL_PACKAGE" ]]; then
  # Query Bazel for transitive source deps
  DEP_DIRS=$(bazel query "deps(${BAZEL_PACKAGE})" --output=package 2>/dev/null \
    | grep -v '^@' \
    | sed 's|^//||' \
    || true)
fi

if [[ -z "$DEP_DIRS" ]]; then
  # Fallback: use chart directory only
  echo >&2 "INFO: Bazel query unavailable or returned no results, using chart dir only"
  DEP_DIRS="$CHART_DIR"
fi

# Convert package paths to -- path arguments for git log
GIT_PATHS=()
while IFS= read -r dir; do
  [[ -n "$dir" ]] && GIT_PATHS+=("$dir")
done <<< "$DEP_DIRS"

# --- Find conventional commits since last version ---
BUMP="none"

while IFS= read -r subject; do
  [[ -z "$subject" ]] && continue

  # Skip automated commits
  case "$subject" in
    *"argocd-image-updater"*|*"ci-format-bot"*|*"chart-version-bot"*) continue ;;
  esac

  # Check for breaking change (! before colon)
  if [[ "$subject" =~ ^[a-z]+(\([^)]*\))?!: ]]; then
    BUMP="major"
    break  # Can't go higher
  fi

  # Check commit type
  TYPE=$(echo "$subject" | sed -n 's/^\([a-z]*\)\(([^)]*)\)\?:.*/\1/p')
  case "$TYPE" in
    feat)
      [[ "$BUMP" != "major" ]] && BUMP="minor"
      ;;
    fix|perf|refactor|style|docs|test|ci|build|chore|revert)
      [[ "$BUMP" == "none" ]] && BUMP="patch"
      ;;
  esac
done < <(git log --format='%an|||%s' "${VERSION_COMMIT}..HEAD" -- "${GIT_PATHS[@]}" 2>/dev/null \
  | grep -v '^\(argocd-image-updater\|ci-format-bot\|chart-version-bot\)|||' \
  | sed 's/^[^|]*|||//')

# --- Apply bump ---
if [[ "$BUMP" == "none" ]]; then
  echo >&2 "INFO: No conventional commits found since ${CURRENT_VERSION}, no bump needed"
  echo "$CURRENT_VERSION"
  exit 0
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo >&2 "INFO: Bumping ${CURRENT_VERSION} -> ${NEW_VERSION} (${BUMP})"
echo "$NEW_VERSION"
```

**Step 2: Make it executable**

Run: `chmod +x bazel/helm/chart-version.sh`

**Step 3: Test it manually against agent-platform chart**

Run: `./bazel/helm/chart-version.sh projects/agent_platform/chart`
Expected: A version like `0.9.0` or `0.8.1` (depending on commits since 0.8.0)

**Step 4: Commit**

```bash
git add bazel/helm/chart-version.sh
git commit -m "feat(helm): add chart-version.sh for conventional commit versioning"
```

---

### Task 2: Update `push.sh.tpl` to call `chart-version.sh`

**Files:**

- Modify: `bazel/helm/push.sh.tpl`

**Step 1: Add version computation and re-packaging logic**

Replace the current push logic with version-aware push. The template gains two new substitutions: `{{CHART_VERSION_SH}}` (path to chart-version.sh) and `{{CHART_DIR}}` (source chart directory).

```bash
#!/usr/bin/env bash
# Push a packaged Helm chart to an OCI registry
# Template substitutions: {{HELM}}, {{CHART_TGZ}}, {{REPOSITORY}}, {{CHART_VERSION_SH}}, {{CHART_DIR}}

set -o errexit -o nounset -o pipefail

# Bazel runfiles setup
RUNFILES_DIR="${RUNFILES_DIR:-}"
if [[ -z "$RUNFILES_DIR" ]]; then
  RUNFILES_DIR="$0.runfiles"
fi

if [[ -f "${RUNFILES_DIR}/bazel_tools/tools/bash/runfiles/runfiles.bash" ]]; then
  source "${RUNFILES_DIR}/bazel_tools/tools/bash/runfiles/runfiles.bash"
elif [[ -f "${RUNFILES_MANIFEST_FILE:-/dev/null}" ]]; then
  source "$(grep -m1 "^bazel_tools/tools/bash/runfiles/runfiles.bash " \
    "$RUNFILES_MANIFEST_FILE" | cut -d ' ' -f 2-)"
else
  echo >&2 "ERROR: cannot find @bazel_tools//tools/bash/runfiles:runfiles.bash"
  exit 1
fi

readonly HELM="$(rlocation "{{HELM}}")"
readonly CHART_TGZ="$(rlocation "{{CHART_TGZ}}")"
REPOSITORY="{{REPOSITORY}}"
CHART_VERSION_SH="{{CHART_VERSION_SH}}"
CHART_DIR="{{CHART_DIR}}"

# Parse command line args
while (( $# > 0 )); do
  case $1 in
    (-r|--repository)
      REPOSITORY="$2"
      shift 2;;
    (--repository=*)
      REPOSITORY="${1#--repository=}"
      shift;;
    (*)
      echo "Unknown argument: $1" >&2
      exit 1;;
  esac
done

# --- Compute next version ---
PUSH_TGZ="$CHART_TGZ"

if [[ -n "$CHART_VERSION_SH" ]] && [[ -n "$CHART_DIR" ]] && [[ -x "$CHART_VERSION_SH" ]]; then
  # Derive Bazel package from chart dir for dependency query
  BAZEL_PKG="//${CHART_DIR}:chart.package"
  CURRENT_VERSION=$(grep '^version:' "${CHART_DIR}/Chart.yaml" | head -1 | awk '{print $2}' | tr -d '"')
  NEW_VERSION=$("$CHART_VERSION_SH" "$CHART_DIR" "$BAZEL_PKG")

  if [[ "$NEW_VERSION" != "$CURRENT_VERSION" ]]; then
    echo "Chart version bump: ${CURRENT_VERSION} -> ${NEW_VERSION}"

    # Re-package with new version
    WORK_DIR=$(mktemp -d)
    tar -xzf "$CHART_TGZ" -C "$WORK_DIR"
    CHART_NAME=$(ls "$WORK_DIR")
    sed -i.bak "s/^version:.*/version: ${NEW_VERSION}/" "$WORK_DIR/$CHART_NAME/Chart.yaml"
    rm -f "$WORK_DIR/$CHART_NAME/Chart.yaml.bak"
    PUSH_TGZ="$WORK_DIR/${CHART_NAME}-${NEW_VERSION}.tgz"
    "$HELM" package "$WORK_DIR/$CHART_NAME" --destination "$WORK_DIR"

    trap "rm -rf '$WORK_DIR'" EXIT
  else
    echo "Chart version unchanged at ${CURRENT_VERSION}"
  fi
fi

echo "Pushing Helm chart: ${PUSH_TGZ}"
echo "  Repository: ${REPOSITORY}"

"${HELM}" push "${PUSH_TGZ}" "${REPOSITORY}"

echo "Successfully pushed chart to ${REPOSITORY}"

# --- Commit version bump back to git ---
if [[ -n "${NEW_VERSION:-}" ]] && [[ "${NEW_VERSION:-}" != "${CURRENT_VERSION:-}" ]]; then
  CHART_YAML="${CHART_DIR}/Chart.yaml"
  if [[ -f "$CHART_YAML" ]]; then
    echo "Committing version bump to ${CHART_YAML}..."
    # macOS sed vs GNU sed: use temp file for portability
    sed "s/^version:.*/version: ${NEW_VERSION}/" "$CHART_YAML" > "${CHART_YAML}.tmp"
    mv "${CHART_YAML}.tmp" "$CHART_YAML"

    CHART_NAME_LOWER=$(grep '^name:' "$CHART_YAML" | head -1 | awk '{print $2}' | tr -d '"')
    git config user.name "chart-version-bot"
    git config user.email "chart-version-bot@users.noreply.github.com"
    git add "$CHART_YAML"
    git commit -m "chore(${CHART_NAME_LOWER}): bump chart version to ${NEW_VERSION}"
    git push origin HEAD:main
    echo "Version bump committed and pushed"
  fi
fi
```

**Step 2: Commit**

```bash
git add bazel/helm/push.sh.tpl
git commit -m "feat(helm): add auto-versioning to push script"
```

---

### Task 3: Update `helm_push` rule and `helm_chart` macro

**Files:**

- Modify: `bazel/helm/push.bzl` (the `_helm_push_impl` and `helm_push` rule)
- Modify: `bazel/helm/chart.bzl` (the `helm_chart` macro)

**Step 1: Add `chart_dir` and `chart_version_sh` to `helm_push`**

In `push.bzl`, update `_helm_push_impl` to pass new substitutions:

```python
def _helm_push_impl(ctx):
    """Push a packaged Helm chart to an OCI registry."""
    push_script = ctx.actions.declare_file(ctx.label.name + ".bash")

    workspace_name = ctx.workspace_name

    # Resolve chart-version.sh path if provided
    chart_version_sh_path = ""
    if ctx.file._chart_version_sh:
        chart_version_sh_path = _rlocationpath(ctx.file._chart_version_sh, workspace_name)

    ctx.actions.expand_template(
        template = ctx.file._push_template,
        output = push_script,
        is_executable = True,
        substitutions = {
            "{{HELM}}": _rlocationpath(ctx.executable._helm, workspace_name),
            "{{CHART_TGZ}}": _rlocationpath(ctx.file.chart, workspace_name),
            "{{REPOSITORY}}": ctx.attr.repository,
            "{{CHART_VERSION_SH}}": chart_version_sh_path,
            "{{CHART_DIR}}": ctx.attr.chart_dir,
        },
    )

    runfiles_files = [ctx.file.chart]
    if ctx.file._chart_version_sh:
        runfiles_files.append(ctx.file._chart_version_sh)

    runfiles = ctx.runfiles(files = runfiles_files)
    runfiles = runfiles.merge(ctx.attr._helm[DefaultInfo].default_runfiles)
    runfiles = runfiles.merge(ctx.attr._runfiles[DefaultInfo].default_runfiles)

    return [DefaultInfo(
        executable = push_script,
        runfiles = runfiles,
    )]
```

Add new attrs to `helm_push`:

```python
helm_push = rule(
    implementation = _helm_push_impl,
    attrs = {
        "chart": attr.label(
            mandatory = True,
            allow_single_file = [".tgz"],
            doc = "Packaged Helm chart (.tgz from helm_package)",
        ),
        "repository": attr.string(
            mandatory = True,
            doc = "OCI repository URL (e.g., oci://ghcr.io/user/repo/charts)",
        ),
        "chart_dir": attr.string(
            default = "",
            doc = "Source chart directory path (for auto-versioning). Empty disables versioning.",
        ),
        "_push_template": attr.label(
            default = "//bazel/helm:push.sh.tpl",
            allow_single_file = True,
        ),
        "_chart_version_sh": attr.label(
            default = "//bazel/helm:chart-version.sh",
            allow_single_file = True,
        ),
        "_helm": attr.label(
            default = "@multitool//tools/helm",
            executable = True,
            cfg = "exec",
        ),
        "_runfiles": attr.label(
            default = "@bazel_tools//tools/bash/runfiles",
        ),
    },
    executable = True,
    doc = "Pushes a packaged Helm chart (.tgz) to an OCI registry.",
)
```

**Step 2: Update `helm_chart` macro to pass `chart_dir`**

In `chart.bzl`, update the `helm_push` call:

```python
        helm_push(
            name = name + ".push",
            chart = name + ".package",
            repository = repository,
            chart_dir = native.package_name(),
            visibility = ["//bazel/images:__pkg__"],
        )
```

**Step 3: Commit**

```bash
git add bazel/helm/push.bzl bazel/helm/chart.bzl
git commit -m "feat(helm): wire chart-version.sh into helm_push rule"
```

---

### Task 4: Add `chart-version-bot` to CI skip lists

**Files:**

- Modify: `buildbuddy.yaml`

**Step 1: Update all author-skip checks**

In each CI action's skip logic, add `chart-version-bot`. There are 4 actions with author checks (Format check, Test, Push images, Push pages). Update each:

```bash
AUTHOR="$(git log -1 --format='%an')"
if [ "$AUTHOR" = "argocd-image-updater" ] || [ "$AUTHOR" = "ci-format-bot" ] || [ "$AUTHOR" = "chart-version-bot" ]; then
  echo "Skipping automated commit from $AUTHOR"
  exit 0
fi
```

**Step 2: Commit**

```bash
git add buildbuddy.yaml
git commit -m "ci: add chart-version-bot to CI skip lists"
```

---

### Task 5: Add BUILD target for `chart-version.sh`

**Files:**

- Modify: `bazel/helm/BUILD` (or create if not exists)

**Step 1: Check if `bazel/helm/BUILD` exists and add exports**

Ensure `chart-version.sh` is visible to the `helm_push` rule:

```python
exports_files(["chart-version.sh"])
```

If `bazel/helm/BUILD` already has content, add this line. If it doesn't exist, create it.

**Step 2: Run `format` to update BUILD files**

Run: `format`

**Step 3: Commit**

```bash
git add bazel/helm/BUILD
git commit -m "build(helm): export chart-version.sh for helm_push"
```

---

### Task 6: End-to-end test on PR

**Step 1: Push branch and create PR**

```bash
git push -u origin feat/chart-auto-version
gh pr create --title "feat(helm): auto-version charts from conventional commits" --body "..."
```

**Step 2: Verify CI passes**

Check BuildBuddy for the Test and Push images actions. The Push images action should:

- Call `chart-version.sh` for each published chart
- Compute a version bump from `0.8.0` → `0.9.0` (or similar)
- Push the chart with the new version
- On main merge: commit back the updated `Chart.yaml`

**Step 3: After merge, verify the version commit appears**

Check git log for a `chore(agent-platform): bump chart version to 0.9.0` commit from `chart-version-bot`.

**Step 4: Verify image updater picks up the new version**

Check that `application.yaml` gets updated with the new `targetRevision` by the ArgoCD Image Updater.
