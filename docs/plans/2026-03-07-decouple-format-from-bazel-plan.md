# Decouple Formatting from Bazel — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all Bazel dependencies from the formatting pipeline so `format` works with standalone binaries from the OCI tools image.

**Architecture:** Formatter binaries (ruff, gofumpt, shfmt, buildifier, prettier) and the custom gazelle binary are added to the `homelab-tools` OCI image. `fast-format.sh` is rewritten to find tools from `$PATH` instead of `bazel build` + `find_bin`. Generate scripts get grep/find-based local implementations with `bazel query` validation in CI. `.envrc` switches from `bazel_env` to `.tools/bin/`.

**Tech Stack:** apko (OCI image), shell scripts, direnv, pre-commit, BuildBuddy CI

**Related:** ADR `architecture/decisions/tooling/001-oci-tool-distribution.md` (this plan implements the formatting subset of that ADR)

---

### Task 1: Add formatter binaries to the OCI tools image

The `homelab-tools` image is built with apko. We need to add formatter packages. The image definition likely lives near the bootstrap or tools area.

**Files:**

- Discover: Find the apko.yaml that builds the `homelab-tools` image (search for `ghcr.io/jomcgi/homelab-tools`)
- Modify: That apko.yaml — add packages for ruff, gofumpt, shfmt, buildifier, prettier

**Step 1: Find the homelab-tools image definition**

```bash
grep -rl "homelab-tools" --include="*.yaml" --include="*.bzl" .
```

If no apko.yaml exists yet for this image, create one at `tools/image/apko.yaml`.

**Step 2: Add formatter packages**

Add to the apko config's `packages:` section. Check Wolfi package availability:

- `ruff` — available in Wolfi as `ruff`
- `gofumpt` — may need `go` ecosystem; check `wolfi-dev` packages
- `shfmt` — available in Wolfi as `shfmt`
- `buildifier` — may need manual binary; check Wolfi
- `prettier` — needs Node.js; consider standalone binary or npm global install

For packages not in Wolfi, use apko's ability to include arbitrary binaries via a local overlay or a pre-build download step.

**Step 3: Verify the image builds**

```bash
bazel build //tools/image:image
```

Or if using standalone apko:

```bash
apko build tools/image/apko.yaml ghcr.io/jomcgi/homelab-tools:dev /tmp/tools-image.tar
```

**Step 4: Commit**

```bash
git add tools/image/
git commit -m "build: add formatter binaries to homelab-tools OCI image"
```

---

### Task 2: Add pre-built gazelle binary to the OCI tools image

The custom gazelle binary includes repo-specific plugins (rules_helm, rules_wrangler, rules_semgrep gazelle extensions). It must be compiled from Go source via Bazel, then included in the tools image.

**Files:**

- Read: `BUILD` (root) — the `gazelle_binary` target definition
- Create: CI step or Bazel target that builds gazelle and stages it for the OCI image

**Step 1: Identify the gazelle binary target**

The root BUILD file defines:

```python
gazelle_binary(
    name = "gazelle_binary",
    languages = [
        "//rules_helm/gazelle",
        "//rules_wrangler/gazelle",
        "//rules_semgrep/gazelle",
        "@bazel_skylib_gazelle_plugin//bzl",
        "@gazelle//language/go",
        "@gazelle//language/proto",
        "@rules_python_gazelle_plugin//python",
    ],
)
```

**Step 2: Create a CI step that builds gazelle and copies it into the image build context**

Add a Bazel target or script that:

1. `bazel build //:gazelle_binary`
2. Copies the output binary to the tools image overlay directory

This could be a `genrule` that produces the binary, or handled in the `buildbuddy.yaml` pipeline before the image build step.

**Step 3: Include the gazelle binary in the apko image**

If apko supports a local overlay directory, place the built binary there. Otherwise, use a multi-stage approach: build gazelle in CI → `crane append` a layer with the binary.

**Step 4: Verify gazelle runs standalone**

```bash
# Extract from image
crane export ghcr.io/jomcgi/homelab-tools:dev - | tar -x tools/bin/gazelle
# Run it
./tools/bin/gazelle --help
```

**Step 5: Commit**

```bash
git add tools/image/ BUILD
git commit -m "build: add pre-built gazelle binary to homelab-tools image"
```

---

### Task 3: Rewrite generate-push-all.sh to use grep/find

Replace `bazel query 'kind("oci_push", //...)'` with grep-based BUILD file scanning.

**Files:**

- Modify: `scripts/generate-push-all.sh`

**Step 1: Write the test — create a validation script**

Create `scripts/validate-generate-scripts.sh` that runs both implementations and diffs output:

```bash
#!/usr/bin/env bash
# Validate that grep-based generate scripts match bazel query output
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Run grep-based version
./scripts/generate-push-all.sh
cp images/BUILD /tmp/push-all-grep.BUILD

# Run bazel query version
OCI_PUSH=$(bazel query 'kind("oci_push", //...)' --output label 2>/dev/null || true)
HELM_PUSH=$(bazel query 'kind("helm_push", //...)' --output label 2>/dev/null || true)
# ... generate BUILD from query output, save to /tmp/push-all-query.BUILD

diff /tmp/push-all-grep.BUILD /tmp/push-all-query.BUILD
echo "✅ generate-push-all: grep matches bazel query"
```

**Step 2: Rewrite `scripts/generate-push-all.sh`**

Replace the `bazel query` calls with grep/find. The pattern to find is `oci_push(` and `helm_push(` in BUILD files, then extract the `name` attribute and construct Bazel labels from the directory path.

Current (lines 13-15):

```bash
OCI_PUSH=$(bazel query 'kind("oci_push", //...)' --output label 2>/dev/null || true)
HELM_PUSH=$(bazel query 'kind("helm_push", //...)' --output label 2>/dev/null || true)
PUSH_TARGETS=$(echo -e "${OCI_PUSH}\n${HELM_PUSH}" | grep -v '^$' | LC_ALL=C sort)
```

New:

```bash
cd "$(git rev-parse --show-toplevel)"

# Find oci_push targets by scanning BUILD files
OCI_PUSH=$(grep -rl 'oci_push(' --include=BUILD --include=BUILD.bazel . \
    | while read -r build_file; do
        dir=$(dirname "$build_file" | sed 's|^\./||')
        grep -oP 'oci_push\(\s*name\s*=\s*"\K[^"]+' "$build_file" | while read -r name; do
            echo "//${dir}:${name}"
        done
    done)

# Find helm_push targets by scanning BUILD files
HELM_PUSH=$(grep -rl 'helm_push(' --include=BUILD --include=BUILD.bazel . \
    | while read -r build_file; do
        dir=$(dirname "$build_file" | sed 's|^\./||')
        grep -oP 'helm_push\(\s*name\s*=\s*"\K[^"]+' "$build_file" | while read -r name; do
            echo "//${dir}:${name}"
        done
    done)

PUSH_TARGETS=$(echo -e "${OCI_PUSH}\n${HELM_PUSH}" | grep -v '^$' | LC_ALL=C sort)
```

Note: macOS `grep` doesn't support `-P` (Perl regex). Use `sed` or `awk` instead:

```bash
grep 'oci_push(' "$build_file" | sed -n 's/.*name *= *"\([^"]*\)".*/\1/p'
```

Also remove the `BUILD_WORKSPACE_DIRECTORY` cd block (lines 6-8) — the script no longer runs via `bazel run`.

**Step 3: Run the script and verify output matches current `images/BUILD`**

```bash
# Save current
cp images/BUILD /tmp/images-BUILD-before
# Run new script
./scripts/generate-push-all.sh
# Diff
diff /tmp/images-BUILD-before images/BUILD
```

**Step 4: Commit**

```bash
git add scripts/generate-push-all.sh
git commit -m "refactor: rewrite generate-push-all to use grep instead of bazel query"
```

---

### Task 4: Rewrite generate-push-all-pages.sh to use grep/find

Same pattern as Task 3 but for `wrangler_pages_push` targets.

**Files:**

- Modify: `scripts/generate-push-all-pages.sh`

**Step 1: Rewrite the script**

Replace (line 13):

```bash
PUSH_TARGETS=$(bazel query 'kind("wrangler_pages_push", //...)' --output label 2>/dev/null | LC_ALL=C sort || true)
```

With:

```bash
cd "$(git rev-parse --show-toplevel)"
PUSH_TARGETS=$(grep -rl 'wrangler_pages_push(' --include=BUILD --include=BUILD.bazel . \
    | while read -r build_file; do
        dir=$(dirname "$build_file" | sed 's|^\./||')
        grep 'wrangler_pages_push(' "$build_file" \
            | sed -n 's/.*name *= *"\([^"]*\)".*/\1/p' \
            | while read -r name; do
                echo "//${dir}:${name}"
            done
    done | LC_ALL=C sort)
```

Remove the `BUILD_WORKSPACE_DIRECTORY` block.

**Step 2: Verify output matches current `websites/BUILD`**

```bash
cp websites/BUILD /tmp/websites-BUILD-before
./scripts/generate-push-all-pages.sh
diff /tmp/websites-BUILD-before websites/BUILD
```

**Step 3: Commit**

```bash
git add scripts/generate-push-all-pages.sh
git commit -m "refactor: rewrite generate-push-all-pages to use grep instead of bazel query"
```

---

### Task 5: Rewrite generate-render-all.sh to use grep/find

Same pattern but for `render_manifests` genrule targets in `overlays/`.

**Files:**

- Modify: `scripts/generate-render-all.sh`

**Step 1: Rewrite the script**

Replace (line 17):

```bash
RENDER_TARGETS=$(bazel query 'kind("genrule", //overlays/...) intersect attr("name", "render_manifests", //overlays/...)' --output label 2>/dev/null | sort)
```

With:

```bash
cd "$(git rev-parse --show-toplevel)"
RENDER_TARGETS=$(grep -rl 'name = "render_manifests"' overlays/ --include=BUILD --include=BUILD.bazel \
    | while read -r build_file; do
        dir=$(dirname "$build_file" | sed 's|^\./||')
        echo "//${dir}:render_manifests"
    done | sort)
```

Also replace the buildifier call at the end (line 55):

```bash
# Old: bazel run @buildifier_prebuilt//:buildifier -- "$BUILD_FILE" 2>/dev/null
# New: use standalone buildifier from PATH
buildifier "$BUILD_FILE" 2>/dev/null
```

Remove the `BUILD_WORKSPACE_DIRECTORY` block.

**Step 2: Verify output matches current `tools/argocd-parallel/BUILD`**

```bash
cp tools/argocd-parallel/BUILD /tmp/render-BUILD-before
./scripts/generate-render-all.sh
diff /tmp/render-BUILD-before tools/argocd-parallel/BUILD
```

**Step 3: Commit**

```bash
git add scripts/generate-render-all.sh
git commit -m "refactor: rewrite generate-render-all to use grep instead of bazel query"
```

---

### Task 6: Create CI validation script for generate scripts

CI runs the `bazel query` versions as a cross-check against the grep-based local scripts.

**Files:**

- Create: `scripts/validate-generate-scripts.sh`

**Step 1: Write the validation script**

```bash
#!/usr/bin/env bash
# CI-only: validate grep-based generate scripts match bazel query output
# This ensures the local grep approximations haven't drifted from reality.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ERRORS=0

validate() {
    local description="$1" query="$2" grep_output="$3"
    local query_output
    query_output=$(eval "$query" 2>/dev/null | sort)

    if [ "$query_output" != "$grep_output" ]; then
        echo "❌ $description: grep output differs from bazel query"
        diff <(echo "$query_output") <(echo "$grep_output") || true
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ $description: matches"
    fi
}

# ... validate each generate script against its bazel query equivalent

exit $ERRORS
```

**Step 2: Commit**

```bash
git add scripts/validate-generate-scripts.sh
git commit -m "ci: add validation script for grep-based generate scripts"
```

---

### Task 7: Rewrite fast-format.sh to use standalone binaries

This is the main change — replace the Bazel-dependent format script with one that uses tools from `$PATH`.

**Files:**

- Modify: `tools/format/fast-format.sh`

**Step 1: Rewrite the script**

Replace the entire script. Key changes:

- Remove `bazel build` call (lines 16-25)
- Remove `find_bin()` function (lines 30-36)
- Find tools via `command -v` or direct `$PATH` lookup
- Remove `bazel run //:gazelle` — call `gazelle` directly
- Keep the same parallel execution pattern

New `tools/format/fast-format.sh`:

```bash
#!/usr/bin/env bash
# Fast format script - runs all formatters in parallel using standalone binaries
# Used by both pre-commit and CI for identical formatting
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1" >&2; }

# Verify required tools are available
MISSING=()
for tool in ruff shfmt buildifier prettier gofumpt gazelle; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING+=("$tool")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    err "Missing tools: ${MISSING[*]}"
    err "Run './bootstrap.sh' to install dev tools"
    exit 1
fi

# Run formatters and script generators in parallel
log "Formatting..."
PIDS=()

# Python
ruff format . 2>/dev/null &
PIDS+=($!)

# Shell
(find . -name '*.sh' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
    xargs -0 shfmt -w 2>/dev/null || true) &
PIDS+=($!)

# Starlark
(find . \( -name BUILD -o -name BUILD.bazel -o -name '*.bzl' -o -name WORKSPACE -o -name WORKSPACE.bazel \) \
    -not -path './bazel-*' -not -path './.claude/worktrees/*' -print0 |
    xargs -0 buildifier 2>/dev/null || true) &
PIDS+=($!)

# Go
(find . -name '*.go' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
    xargs -0 gofumpt -w 2>/dev/null || true) &
PIDS+=($!)

# Prettier (JS/TS/JSON/YAML/MD)
prettier --write . 2>/dev/null &
PIDS+=($!)

# Script generators (grep-based, no Bazel needed)
./scripts/generate-push-all.sh 2>/dev/null &
PIDS+=($!)
./scripts/generate-push-all-pages.sh 2>/dev/null &
PIDS+=($!)
./scripts/generate-render-all.sh &
PIDS+=($!)

# Wait for all parallel tasks
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

# Gazelle (generates BUILD files for Go/Python/Helm/etc.)
# Run after formatters complete since it needs formatted source files
log "Running gazelle..."
gazelle 2>/dev/null || true

log "Done!"
```

**Step 2: Verify the script runs and produces the same output**

```bash
# Save current state
git stash
# Run old format
format
git diff > /tmp/old-format.diff
git checkout .
# Run new format
./tools/format/fast-format.sh
git diff > /tmp/new-format.diff
# Compare
diff /tmp/old-format.diff /tmp/new-format.diff
```

**Step 3: Commit**

```bash
git add tools/format/fast-format.sh
git commit -m "refactor: rewrite fast-format.sh to use standalone binaries from PATH"
```

---

### Task 8: Update .envrc to use .tools/bin instead of bazel_env

**Files:**

- Modify: `.envrc`

**Step 1: Replace the PATH setup**

Current `.envrc`:

```bash
export ORION_EXTENSIONS_DIR=$PWD/.aspect/gazelle/

watch_file bazel-out/bazel_env-opt/bin/tools/bazel_env/bin
PATH_add bazel-out/bazel_env-opt/bin/tools/bazel_env/bin
if [[ ! -d bazel-out/bazel_env-opt/bin/tools/bazel_env/bin ]]; then
  log_error "ERROR[bazel_env.bzl]: Run 'bazel run //tools:bazel_env' to regenerate ..."
fi
```

New `.envrc`:

```bash
export ORION_EXTENSIONS_DIR=$PWD/.aspect/gazelle/

TOOLS_DIR="$PWD/.tools/bin"
if [[ ! -d "$TOOLS_DIR" ]]; then
  log_error "ERROR: Run './bootstrap.sh' to install dev tools"
fi
PATH_add "$TOOLS_DIR"
```

**Step 2: Verify direnv reloads and tools are found**

```bash
direnv allow
which format
which ruff
which gazelle
```

**Step 3: Commit**

```bash
git add .envrc
git commit -m "build: switch .envrc from bazel_env to .tools/bin"
```

---

### Task 9: Update CI format check in buildbuddy.yaml

CI needs to use the standalone format script. It also needs to run the generate script validation.

**Files:**

- Modify: `buildbuddy.yaml`

**Step 1: Update the format check step**

Replace (line 23):

```bash
bazel run //tools/format:fast_format
```

With:

```bash
# Install standalone tools (CI environment)
./bootstrap.sh || true  # May need adaptation for Linux CI
# Run standalone format
./tools/format/fast-format.sh
# Validate generate scripts against bazel query (authoritative check)
./scripts/validate-generate-scripts.sh
```

Note: `bootstrap.sh` is macOS-only. For CI (Linux), the tools may need to be available differently — either pre-installed in the BuildBuddy container image, or `bootstrap.sh` needs a Linux path. Check how the CI environment works and adapt.

Alternative: Keep `bazel run //tools/format:fast_format` in CI (Bazel is available there) and only use standalone locally. The generate validation script would still run in CI.

**Step 2: Commit**

```bash
git add buildbuddy.yaml
git commit -m "ci: update format check to use standalone tools + generate validation"
```

---

### Task 10: Update Claude skill and CLAUDE.md

**Files:**

- Modify: `.claude/skills/bazel/SKILL.md`
- Modify: `CLAUDE.md`

**Step 1: Update the bazel skill**

In `.claude/skills/bazel/SKILL.md`, update the "Format and Render" section:

Change:

````markdown
### Format and Render (Most Common)

```bash
format
```
````

This runs multiple tasks in parallel:

- Updates apko lock files
- Validates apko configs
- Formats Go, Python, JS, Shell code
- Renders all Helm charts to manifests/all.yaml

````

To:
```markdown
### Format (Most Common)

```bash
format
````

This runs standalone formatter binaries in parallel (no Bazel required):

- Formats Go (gofumpt), Python (ruff), JS/JSON/YAML (prettier), Shell (shfmt), Starlark (buildifier)
- Regenerates push/render BUILD files via grep-based scripts
- Runs gazelle to update BUILD files for Go/Python/Helm

Tools are provided by the OCI tools image via `./bootstrap.sh`.

````

Remove `//tools/format:format` and `//tools/format:fast_format` from the Key Targets table.

**Step 2: Update CLAUDE.md Essential Commands**

In the "Essential Commands" section, update:
```bash
format                        # Format code + update BUILD files (standalone, no Bazel needed)
````

Add a note that `format` requires `./bootstrap.sh` to have been run.

**Step 3: Commit**

```bash
git add .claude/skills/bazel/SKILL.md CLAUDE.md
git commit -m "docs: update skill and CLAUDE.md for standalone formatting"
```

---

### Task 11: Clean up Claude permissions (settings.json and settings.local.json)

**Files:**

- Modify: `.claude/settings.json` — minimal changes (permissions already work since `format` is still in PATH)
- Modify: `.claude/settings.local.json` — remove stale bazel-format entries

**Step 1: Review and clean settings.json**

The `Bash(format:*)` permission in `.claude/settings.json:62` already works since `format` remains a PATH command. No change needed.

Consider removing `Bash(bazelisk:*)` if Bazel is no longer needed locally — but this is a broader change beyond just formatting. Leave it for now.

**Step 2: Clean settings.local.json**

Remove entries that reference Bazel-based formatting:

- `"Bash(RUFF=bazel-bin/external/rules_multitool++multitool+multitool/tools/ruff/ruff:*)"` — stale
- `"Bash(\"$RUFF\" format --check services/ais-ingest/main.py)"` — stale

**Step 3: Commit**

```bash
git add .claude/settings.local.json
git commit -m "chore: remove stale bazel-format permissions from settings"
```

---

### Task 12: Update pre-commit hook entries

**Files:**

- Modify: `.pre-commit-config.yaml` (if needed)
- Modify: `tools/format/update-apko-locks.sh`
- Modify: `tools/format/update-python-requirements.sh`
- Modify: `tools/format/update-python-requirements-if-needed.sh`

**Step 1: Check pre-commit format-code hook**

The `format-code` hook at `.pre-commit-config.yaml:15-20` calls `tools/format/fast-format.sh` directly. Since we rewrote the script in Task 7, this works without changes.

**Step 2: Check apko and python requirement hooks**

These hooks (`update-apko-locks.sh`, `update-python-requirements.sh`) still use `bazel run` commands. These are separate from the core format pipeline and run conditionally (only when `apko.yaml` or `pyproject.toml` changes). They can remain Bazel-dependent for now — they're lock file operations that genuinely need Bazel (apko rules, pip rules).

Document this in a comment in the scripts: "These still require Bazel — see ADR 001 Phase 4 for full Bazel removal."

**Step 3: Commit (if any changes)**

```bash
git add .pre-commit-config.yaml tools/format/
git commit -m "docs: annotate remaining bazel-dependent format hooks"
```

---

### Task 13: End-to-end verification

**Step 1: Run bootstrap to get tools**

```bash
./bootstrap.sh
direnv allow
```

**Step 2: Run format and verify it works without Bazel**

```bash
# Ensure no bazel processes are running
bazel shutdown 2>/dev/null || true

# Run format
format

# Verify no errors
echo $?
```

**Step 3: Verify pre-commit hook works**

```bash
# Make a trivial change
echo "" >> README.md
git add README.md
git commit -m "test: verify pre-commit runs standalone format"
# Should pass without bazel
```

**Step 4: Verify CI would pass**

```bash
# Check for drift
git diff --exit-code
```

**Step 5: Clean up test commit**

```bash
git reset HEAD~1
git checkout README.md
```
