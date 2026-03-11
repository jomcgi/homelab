# Helm Manifest Diff Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A BuildBuddy CI action that renders Helm manifests from main and the PR branch, diffs them with dyff, and posts a self-updating PR comment with collapsible sections per changed app.

**Architecture:** A standalone shell script (`bazel/helm/ci-diff-manifests.sh`) discovers all ArgoCD applications by finding `application.yaml` files, parses chart path / release name / namespace / values files from each, renders manifests from both `origin/main` (via `git show`) and the PR working tree, then diffs with `dyff between`. A new BuildBuddy action triggers this on PRs.

**Tech Stack:** Bash, Helm (multitool), dyff (multitool, new), gh (multitool), BuildBuddy CI

---

### Task 1: Add dyff to rules_multitool

**Files:**

- Modify: `bazel/tools/tools.lock.json`
- Modify: `MODULE.bazel:54-93` (multitool use_repo block)

**Step 1: Add dyff to tools.lock.json**

Add after the `crane` entry (alphabetical order). dyff v1.11.2 archives contain `dyff` at the tarball root.

```json
  "dyff": {
    "binaries": [
      {
        "kind": "archive",
        "url": "https://github.com/homeport/dyff/releases/download/v1.11.2/dyff_1.11.2_linux_arm64.tar.gz",
        "file": "dyff",
        "sha256": "132cecbf4982628e8d47e30f5d25f987bb3f0a73a19fd1f1f23108559f1fb2f6",
        "os": "linux",
        "cpu": "arm64"
      },
      {
        "kind": "archive",
        "url": "https://github.com/homeport/dyff/releases/download/v1.11.2/dyff_1.11.2_linux_amd64.tar.gz",
        "file": "dyff",
        "sha256": "84e952f8ac40c8824de83d81261f9f6c5b984b5ff367eb08b688e0c1450a4f85",
        "os": "linux",
        "cpu": "x86_64"
      },
      {
        "kind": "archive",
        "url": "https://github.com/homeport/dyff/releases/download/v1.11.2/dyff_1.11.2_darwin_arm64.tar.gz",
        "file": "dyff",
        "sha256": "1bdb0e5e26302d976ea4a0fdd19cb25b0b2f765c8dc63cdd6b4f243027be8775",
        "os": "macos",
        "cpu": "arm64"
      }
    ]
  },
```

**Step 2: Register dyff repos in MODULE.bazel**

Add to the `use_repo(multitool, ...)` block after the `crane` entries:

```starlark
    "multitool.dyff.linux_arm64",
    "multitool.dyff.linux_x86_64",
    "multitool.dyff.macos_arm64",
```

**Step 3: Verify Bazel can resolve dyff**

Run: `bazel build @multitool//tools/dyff`
Expected: BUILD SUCCESS (downloads and extracts the dyff binary)

**Step 4: Commit**

```bash
git add bazel/tools/tools.lock.json MODULE.bazel
git commit -m "build: add dyff to rules_multitool"
```

---

### Task 2: Write ci-diff-manifests.sh

**Files:**

- Create: `bazel/helm/ci-diff-manifests.sh`

This is the main script. It has five phases:

1. **Setup** — build tools via Bazel, set up temp dirs
2. **Discover** — find all `application.yaml` files, parse helm config
3. **Render main** — reconstruct charts/values from `origin/main` via `git show`, render
4. **Render PR** — render from working tree
5. **Diff & comment** — dyff between, build markdown, post/update PR comment

**Step 1: Create the script**

```bash
#!/usr/bin/env bash
# ci-diff-manifests.sh — Render Helm manifests from main and PR, diff with dyff,
# post a PR comment with collapsible sections per changed app.
#
# Usage: ./bazel/helm/ci-diff-manifests.sh
#
# Requires: BUILDBUDDY_PULL_REQUEST_NUMBER env var (set by BuildBuddy on PR builds)
#           GHCR_TOKEN env var (for gh auth, set in BuildBuddy secrets)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── Configuration ──────────────────────────────────────────────────
COMMENT_MARKER="<!-- helm-manifest-diff -->"
MAIN_REF="origin/main"
TMPDIR_BASE=$(mktemp -d)
MAIN_RENDER_DIR="$TMPDIR_BASE/main"
PR_RENDER_DIR="$TMPDIR_BASE/pr"
MAIN_TREE_DIR="$TMPDIR_BASE/main-tree"
mkdir -p "$MAIN_RENDER_DIR" "$PR_RENDER_DIR" "$MAIN_TREE_DIR"

trap 'rm -rf "$TMPDIR_BASE"' EXIT

# ── Phase 1: Setup tools ──────────────────────────────────────────
echo "==> Building tools..."
bazel build @multitool//tools/helm @multitool//tools/dyff @multitool//tools/gh 2>&1 | tail -1
BAZEL_BIN=$(bazel info bazel-bin 2>/dev/null)

HELM=$(find -L "$BAZEL_BIN/external" -name "helm" -type f -perm /111 2>/dev/null | head -1)
DYFF=$(find -L "$BAZEL_BIN/external" -name "dyff" -type f -perm /111 2>/dev/null | head -1)
GH=$(find -L "$BAZEL_BIN/external" -name "gh" -type f -perm /111 2>/dev/null | head -1)

for tool_name in HELM DYFF GH; do
    tool_path="${!tool_name}"
    if [ -z "$tool_path" ]; then
        echo "ERROR: $tool_name not found in bazel-bin"
        exit 1
    fi
    echo "  $tool_name: $tool_path"
done

# Authenticate gh with GHCR_TOKEN (also used for GitHub API)
export GH_TOKEN="${GHCR_TOKEN:-}"
if [ -z "$GH_TOKEN" ]; then
    echo "WARNING: GHCR_TOKEN not set, PR comment will be skipped"
fi

# ── Phase 2: Discover applications ────────────────────────────────
echo ""
echo "==> Discovering ArgoCD applications..."

# parse_app extracts helm config from an application.yaml file.
# Outputs: app_name|chart_path|release_name|namespace|values_file1,values_file2,...
parse_app() {
    local app_file="$1"
    local app_dir
    app_dir=$(dirname "$app_file")

    # Skip multi-source apps (OCI chart references, $values refs)
    if grep -q 'sources:' "$app_file" 2>/dev/null; then
        return
    fi

    # Extract fields using grep/awk — these are simple structured YAML
    local chart_path release_name namespace
    chart_path=$(grep '^\s*path:' "$app_file" | head -1 | awk '{print $2}' | tr -d '"')
    release_name=$(grep '^\s*releaseName:' "$app_file" | head -1 | awk '{print $2}' | tr -d '"')
    namespace=$(awk '/destination:/{found=1} found && /namespace:/{print $2; exit}' "$app_file" | tr -d '"')

    # Fallback: release_name defaults to metadata.name
    if [ -z "$release_name" ]; then
        release_name=$(awk '/^metadata:/{found=1} found && /name:/{print $2; exit}' "$app_file" | tr -d '"')
    fi

    # Extract values files (lines under helm.valueFiles)
    local values_csv=""
    local in_values=false
    while IFS= read -r line; do
        if echo "$line" | grep -q 'valueFiles:'; then
            in_values=true
            continue
        fi
        if $in_values; then
            # Stop at next non-list-item line
            if echo "$line" | grep -qE '^\s*-\s'; then
                local vf
                vf=$(echo "$line" | sed 's/^\s*-\s*//' | tr -d '"' | xargs)
                if [ -n "$values_csv" ]; then
                    values_csv="$values_csv,$vf"
                else
                    values_csv="$vf"
                fi
            else
                in_values=false
            fi
        fi
    done < "$app_file"

    if [ -z "$chart_path" ] || [ -z "$namespace" ]; then
        return
    fi

    echo "${release_name}|${chart_path}|${namespace}|${values_csv}"
}

# Collect all apps
APPS=()
while IFS= read -r app_file; do
    result=$(parse_app "$app_file")
    if [ -n "$result" ]; then
        APPS+=("$result")
    fi
done < <(find projects -name "application.yaml" \
    -not -path "*/home-cluster/*" \
    -not -path "*/charts/*" | sort)

echo "  Found ${#APPS[@]} application(s)"

# ── Phase 3: Render from main ─────────────────────────────────────
echo ""
echo "==> Rendering manifests from $MAIN_REF..."

# Ensure we have the main ref
git fetch origin main --quiet 2>/dev/null || true

render_app() {
    local helm_bin="$1" output_dir="$2" tree_root="$3"
    local app_spec="$4"

    IFS='|' read -r release_name chart_path namespace values_csv <<< "$app_spec"

    local chart_full_path="$tree_root/$chart_path"
    if [ ! -d "$chart_full_path" ]; then
        echo "  SKIP $release_name (chart dir not found: $chart_path)"
        return 1
    fi

    # Build values args
    local values_args=()
    if [ -n "$values_csv" ]; then
        IFS=',' read -ra vfiles <<< "$values_csv"
        for vf in "${vfiles[@]}"; do
            # Resolve relative to chart path
            local resolved="$tree_root/$chart_path/$vf"
            if [ -f "$resolved" ]; then
                values_args+=(--values "$resolved")
            else
                echo "  WARNING: values file not found: $chart_path/$vf"
            fi
        done
    fi

    local output_file="$output_dir/${release_name}.yaml"
    if "$helm_bin" template "$release_name" "$chart_full_path" \
        --namespace "$namespace" \
        "${values_args[@]}" \
        > "$output_file" 2>/dev/null; then
        return 0
    else
        echo "  ERROR rendering $release_name"
        rm -f "$output_file"
        return 1
    fi
}

# Reconstruct main tree using git show
# We only need chart dirs and values files referenced by the apps
reconstruct_main_tree() {
    for app_spec in "${APPS[@]}"; do
        IFS='|' read -r release_name chart_path namespace values_csv <<< "$app_spec"

        # Get list of files in the chart path from main
        local files
        files=$(git ls-tree -r --name-only "$MAIN_REF" -- "$chart_path" 2>/dev/null) || continue

        while IFS= read -r file; do
            local dest="$MAIN_TREE_DIR/$file"
            mkdir -p "$(dirname "$dest")"
            git show "$MAIN_REF:$file" > "$dest" 2>/dev/null || true
        done <<< "$files"
    done
}

reconstruct_main_tree

main_ok=0
main_fail=0
for app_spec in "${APPS[@]}"; do
    IFS='|' read -r release_name _ _ _ <<< "$app_spec"
    if render_app "$HELM" "$MAIN_RENDER_DIR" "$MAIN_TREE_DIR" "$app_spec"; then
        ((main_ok++))
    else
        ((main_fail++))
    fi
done
echo "  Rendered: $main_ok ok, $main_fail failed/skipped"

# ── Phase 4: Render from PR ───────────────────────────────────────
echo ""
echo "==> Rendering manifests from PR branch..."

pr_ok=0
pr_fail=0
for app_spec in "${APPS[@]}"; do
    IFS='|' read -r release_name _ _ _ <<< "$app_spec"
    if render_app "$HELM" "$PR_RENDER_DIR" "$REPO_ROOT" "$app_spec"; then
        ((pr_ok++))
    else
        ((pr_fail++))
    fi
done
echo "  Rendered: $pr_ok ok, $pr_fail failed/skipped"

# ── Phase 5: Diff and post comment ────────────────────────────────
echo ""
echo "==> Comparing manifests..."

DIFF_BODY=""
CHANGED_COUNT=0
TOTAL_COUNT=0

for app_spec in "${APPS[@]}"; do
    IFS='|' read -r release_name _ _ _ <<< "$app_spec"

    main_file="$MAIN_RENDER_DIR/${release_name}.yaml"
    pr_file="$PR_RENDER_DIR/${release_name}.yaml"

    # Handle cases where one side failed to render
    if [ ! -f "$main_file" ] && [ ! -f "$pr_file" ]; then
        continue
    fi

    ((TOTAL_COUNT++))

    if [ ! -f "$main_file" ]; then
        ((CHANGED_COUNT++))
        DIFF_BODY+="<details>
<summary><code>${release_name}</code> — new application</summary>

\`\`\`yaml
$(head -50 "$pr_file")
\`\`\`
*(truncated — showing first 50 lines)*

</details>

"
        continue
    fi

    if [ ! -f "$pr_file" ]; then
        ((CHANGED_COUNT++))
        DIFF_BODY+="<details>
<summary><code>${release_name}</code> — removed application</summary>

Application was removed or failed to render on the PR branch.

</details>

"
        continue
    fi

    # Run dyff
    local_diff=$("$DYFF" between --omit-header "$main_file" "$pr_file" 2>/dev/null) || true

    if [ -n "$local_diff" ]; then
        ((CHANGED_COUNT++))
        echo "  CHANGED: $release_name"
        DIFF_BODY+="<details>
<summary><code>${release_name}</code></summary>

\`\`\`diff
${local_diff}
\`\`\`

</details>

"
    fi
done

echo ""
echo "  $CHANGED_COUNT of $TOTAL_COUNT application(s) have manifest changes"

# Build the full comment
if [ "$CHANGED_COUNT" -eq 0 ]; then
    COMMENT="${COMMENT_MARKER}
## Helm Manifest Diff

No manifest changes detected across $TOTAL_COUNT application(s)."
else
    COMMENT="${COMMENT_MARKER}
## Helm Manifest Diff

**$CHANGED_COUNT** of **$TOTAL_COUNT** application(s) have manifest changes.

${DIFF_BODY}"
fi

# Post or update PR comment
PR_NUMBER="${BUILDBUDDY_PULL_REQUEST_NUMBER:-}"
if [ -z "$PR_NUMBER" ]; then
    echo ""
    echo "No PR number found (not a PR build?). Printing diff to stdout:"
    echo ""
    echo "$COMMENT"
    exit 0
fi

if [ -z "$GH_TOKEN" ]; then
    echo ""
    echo "No GH_TOKEN — skipping PR comment. Diff output:"
    echo ""
    echo "$COMMENT"
    exit 0
fi

echo ""
echo "==> Posting PR comment..."

# Find existing comment by marker
EXISTING_COMMENT_ID=$("$GH" api \
    "repos/{owner}/{repo}/issues/${PR_NUMBER}/comments" \
    --jq ".[] | select(.body | startswith(\"$COMMENT_MARKER\")) | .id" \
    2>/dev/null | head -1) || true

if [ -n "$EXISTING_COMMENT_ID" ]; then
    echo "  Updating existing comment $EXISTING_COMMENT_ID"
    "$GH" api \
        "repos/{owner}/{repo}/issues/comments/${EXISTING_COMMENT_ID}" \
        --method PATCH \
        --field body="$COMMENT" \
        --silent
else
    echo "  Creating new comment"
    "$GH" pr comment "$PR_NUMBER" --body "$COMMENT"
fi

echo "Done!"
```

**Step 2: Make it executable**

```bash
chmod +x bazel/helm/ci-diff-manifests.sh
```

**Step 3: Test locally (dry run)**

Run: `./bazel/helm/ci-diff-manifests.sh`
Expected: Script discovers apps, renders from main and working tree, prints diff to stdout (no PR number set, so it won't try to post a comment).

**Step 4: Commit**

```bash
git add bazel/helm/ci-diff-manifests.sh
git commit -m "feat: add helm manifest diff script for PR review"
```

---

### Task 3: Add BuildBuddy CI action

**Files:**

- Modify: `buildbuddy.yaml`

**Step 1: Add the manifest diff action**

Add after the "Push pages" action at the end of `buildbuddy.yaml`:

```yaml
# Manifest diff — renders Helm manifests from main and PR, posts diff as PR comment
# Runs in parallel with other actions (no depends_on), non-blocking (informational only)
- name: "Manifest diff"
  container_image: "ubuntu-24.04"
  max_retries: 1
  resource_requests:
    disk: "20GB"
  triggers:
    pull_request:
      branches:
        - "*"
      merge_with_base: false
  steps:
    - run: ./bazel/helm/ci-diff-manifests.sh
```

**Step 2: Commit**

```bash
git add buildbuddy.yaml
git commit -m "ci: add manifest diff action for PR review comments"
```

---

### Task 4: Push and create PR

**Step 1: Push the branch**

```bash
git push -u origin feat/helm-manifest-diff
```

**Step 2: Create PR**

```bash
gh pr create \
    --title "feat: helm manifest diff for PR review" \
    --body "$(cat <<'EOF'
## Summary

- Adds `dyff` to `rules_multitool` for structured YAML diffing
- Adds `bazel/helm/ci-diff-manifests.sh` that discovers all ArgoCD apps,
  renders manifests from main and the PR branch, and diffs with dyff
- Adds a "Manifest diff" BuildBuddy CI action that runs on PRs and posts
  a self-updating comment with collapsible sections per changed app

## Test plan

- [ ] CI passes (format, test)
- [ ] The "Manifest diff" action runs and posts a comment on this PR
- [ ] The comment shows collapsible sections for any apps with changes
- [ ] Pushing again updates the existing comment (doesn't create a new one)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Verify the PR's own manifest diff comment appears**

Poll `gh pr view --json state,statusCheckRollup` until CI completes, then check the PR for the manifest diff comment.

---

### Edge Cases to Handle

1. **Multi-source apps** (like `agent-platform` with OCI chart ref): `parse_app` detects `sources:` (plural) and skips them. These can't be rendered locally without pulling from the OCI registry.

2. **New apps in PR**: The main-side render will fail (chart doesn't exist on main), so the diff shows "new application" with the first 50 lines of rendered output.

3. **Deleted apps in PR**: The PR-side render will fail, showing "removed application".

4. **Missing `releaseName`**: Falls back to `metadata.name` from the application.yaml.

5. **Values files referencing parent dirs** (e.g. `../deploy/values.yaml`): Resolved relative to chart path, which is correct since that's how ArgoCD resolves them too.

6. **Large diffs**: dyff output is naturally compact (shows only changed paths), but very large chart changes could produce long output. GitHub truncates comments at 65536 chars — if this becomes an issue, we can add truncation later.
