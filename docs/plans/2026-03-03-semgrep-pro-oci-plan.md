# Semgrep Pro OCI Artifacts — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Distribute Semgrep Pro engine and rule packs as separate OCI artifacts on GHCR, consumed by Bazel via a custom repository rule, with a daily GHA workflow that auto-updates digests via PR.

**Architecture:** A `oci_archive` repository rule fetches OCI artifacts from GHCR using the OCI Distribution HTTP API (curl for auth/manifest, `repository_ctx.download()` for blobs). A module extension reads digest pins from `digests.bzl` and creates repos for each artifact. A GHA workflow downloads pro engine + rules, pushes to GHCR, and opens automerge PRs when digests change.

**Tech Stack:** Bazel bzlmod (repository rules, module extensions), OCI Distribution API, crane, GitHub Actions, GHCR

**Design doc:** `docs/plans/2026-03-03-semgrep-pro-oci-design.md`

---

## Prerequisites

Before starting implementation:

1. Add `SEMGREP_APP_TOKEN` to GitHub repo secrets (Settings > Secrets and variables > Actions)
2. Verify `GITHUB_TOKEN` has `packages:write` scope (default for repo-owned workflows)

---

### Task 1: Create `oci_archive` repository rule

This repository rule fetches a single OCI artifact from GHCR and extracts its filesystem layer. It's the building block — the module extension (Task 2) calls it once per artifact.

**Files:**
- Create: `third_party/semgrep_pro/oci_archive.bzl`
- Create: `third_party/semgrep_pro/BUILD`

**Step 1: Create the BUILD file**

```starlark
# third_party/semgrep_pro/BUILD
load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

bzl_library(
    name = "oci_archive",
    srcs = ["oci_archive.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "extensions",
    srcs = [
        "digests.bzl",
        "extensions.bzl",
    ],
    visibility = ["//visibility:public"],
    deps = [":oci_archive"],
)

# Platform-aware alias for the pro engine binary
# Consumers use //third_party/semgrep_pro:engine
alias(
    name = "engine",
    actual = select({
        "@platforms//cpu:x86_64": "@semgrep_pro_engine_amd64//:engine",
        "@platforms//cpu:aarch64": "@semgrep_pro_engine_arm64//:engine",
    }),
    visibility = ["//visibility:public"],
)
```

**Step 2: Implement the repository rule**

The rule implements a minimal OCI Distribution client:
1. Exchange GitHub token for a GHCR bearer token (needs Basic auth → curl)
2. Fetch the OCI manifest by digest (needs Accept header → curl)
3. Download the layer blob (large file → `repository_ctx.download()` would be ideal but GHCR redirects break auth, so use curl -L)
4. Extract the tarball and generate a BUILD file

```starlark
# third_party/semgrep_pro/oci_archive.bzl
"""Repository rule to fetch and extract an OCI artifact from GHCR.

Implements a minimal OCI Distribution client: token exchange, manifest
fetch, and layer blob download. Designed for single-layer artifacts
pushed via `crane append`.
"""

_GHCR_REGISTRY = "ghcr.io"

def _get_ghcr_token(rctx, image, github_token):
    """Exchange GitHub credentials for a GHCR bearer token."""
    result = rctx.execute([
        "curl", "-sf",
        "-u", "jomcgi:" + github_token,
        "https://{}/token?service={}&scope=repository:{}:pull".format(
            _GHCR_REGISTRY,
            _GHCR_REGISTRY,
            image,
        ),
    ])
    if result.return_code != 0:
        fail("GHCR token exchange failed for {}: {}".format(image, result.stderr))
    return json.decode(result.stdout)["token"]

def _fetch_manifest(rctx, image, digest, token):
    """Fetch an OCI image manifest by digest."""
    result = rctx.execute([
        "curl", "-sf",
        "-H", "Authorization: Bearer " + token,
        "-H", "Accept: application/vnd.oci.image.manifest.v1+json",
        "https://{}/v2/{}/manifests/{}".format(_GHCR_REGISTRY, image, digest),
    ])
    if result.return_code != 0:
        fail("Failed to fetch manifest for {}@{}: {}".format(image, digest, result.stderr))
    return json.decode(result.stdout)

def _download_and_extract_layer(rctx, image, layer, token):
    """Download a layer blob and extract it."""
    layer_digest = layer["digest"]
    media_type = layer.get("mediaType", "")

    # Determine file extension from mediaType
    if "+gzip" in media_type:
        filename = "_layer.tar.gz"
    elif "+zstd" in media_type:
        filename = "_layer.tar.zst"
    else:
        filename = "_layer.tar"

    blob_url = "https://{}/v2/{}/blobs/{}".format(_GHCR_REGISTRY, image, layer_digest)

    # Use curl -L because GHCR redirects blob downloads to a CDN,
    # which breaks repository_ctx.download() auth pattern matching.
    result = rctx.execute(
        ["curl", "-sfL", "-H", "Authorization: Bearer " + token, "-o", filename, blob_url],
        timeout = 600,
    )
    if result.return_code != 0:
        fail("Failed to download layer {}: {}".format(layer_digest, result.stderr))

    rctx.extract(archive = filename, stripPrefix = rctx.attr.strip_prefix)
    rctx.delete(filename)

def _oci_archive_impl(rctx):
    digest = rctx.attr.digest
    image = rctx.attr.image

    # Empty digest = create empty repo (for initial setup before first GHA run)
    if not digest:
        rctx.file("BUILD.bazel", rctx.attr.build_file_content or """\
filegroup(
    name = "files",
    srcs = [],
    visibility = ["//visibility:public"],
)
""")
        return

    github_token = rctx.os.environ.get("GITHUB_TOKEN", "") or rctx.os.environ.get("GHCR_TOKEN", "")
    if not github_token:
        fail("GITHUB_TOKEN or GHCR_TOKEN required to fetch " + image)

    token = _get_ghcr_token(rctx, image, github_token)
    manifest = _fetch_manifest(rctx, image, digest, token)

    if not manifest.get("layers"):
        fail("Manifest for {} has no layers".format(image))

    _download_and_extract_layer(rctx, image, manifest["layers"][0], token)
    rctx.file("BUILD.bazel", rctx.attr.build_file_content or """\
filegroup(
    name = "files",
    srcs = glob(["**/*"]),
    visibility = ["//visibility:public"],
)
""")

oci_archive = repository_rule(
    implementation = _oci_archive_impl,
    attrs = {
        "image": attr.string(
            mandatory = True,
            doc = "GHCR image path without registry prefix (e.g. jomcgi/homelab/tools/semgrep-pro/engine-amd64)",
        ),
        "digest": attr.string(
            doc = "OCI manifest digest (sha256:...). Empty string creates an empty repo.",
        ),
        "build_file_content": attr.string(
            doc = "Custom BUILD.bazel content for the extracted files.",
        ),
        "strip_prefix": attr.string(
            doc = "Directory prefix to strip from the extracted archive.",
        ),
    },
    environ = ["GITHUB_TOKEN", "GHCR_TOKEN"],
    doc = "Fetches an OCI artifact from GHCR and extracts its filesystem layer.",
)
```

**Step 3: Verify BUILD loads cleanly**

Run: `cd /tmp/claude-worktrees/semgrep-pro-oci && bazel build //third_party/semgrep_pro:oci_archive`
Expected: SUCCESS (bzl_library compiles)

**Step 4: Commit**

```bash
git add third_party/semgrep_pro/
git commit -m "feat: add oci_archive repository rule for GHCR artifacts"
```

---

### Task 2: Create module extension and digest pins

The module extension reads `digests.bzl` and creates repository rule instances for each artifact. This keeps MODULE.bazel clean — only the extension registration and `use_repo` list.

**Files:**
- Create: `third_party/semgrep_pro/digests.bzl`
- Create: `third_party/semgrep_pro/extensions.bzl`

**Step 1: Create digests.bzl with empty placeholders**

```starlark
# third_party/semgrep_pro/digests.bzl
"""Semgrep Pro OCI artifact digests.

Updated automatically by .github/workflows/update-semgrep-pro.yaml.
Do not edit manually — changes will be overwritten.
"""

SEMGREP_PRO_DIGESTS = {
    "engine_amd64": "",
    "engine_arm64": "",
    "rules_golang": "",
    "rules_python": "",
    "rules_javascript": "",
    "rules_kubernetes": "",
}
```

**Step 2: Create extensions.bzl**

```starlark
# third_party/semgrep_pro/extensions.bzl
"""Module extension for Semgrep Pro OCI artifacts.

Creates repository rules for the pro engine (per-platform) and
per-language rule packs. Reads digest pins from digests.bzl.
"""

load(":digests.bzl", "SEMGREP_PRO_DIGESTS")
load(":oci_archive.bzl", "oci_archive")

_GHCR_PREFIX = "jomcgi/homelab/tools/semgrep-pro"

_ENGINE_BUILD = """\
exports_files(["semgrep-core-proprietary"])

filegroup(
    name = "engine",
    srcs = ["semgrep-core-proprietary"],
    visibility = ["//visibility:public"],
)
"""

_RULES_BUILD = """\
filegroup(
    name = "rules",
    srcs = glob(["*.yaml"]),
    visibility = ["//visibility:public"],
)
"""

def _semgrep_pro_impl(module_ctx):
    # Engine binary — one repo per platform
    for platform in ["amd64", "arm64"]:
        oci_archive(
            name = "semgrep_pro_engine_" + platform,
            image = _GHCR_PREFIX + "/engine-" + platform,
            digest = SEMGREP_PRO_DIGESTS.get("engine_" + platform, ""),
            build_file_content = _ENGINE_BUILD,
        )

    # Rule packs — one repo per language
    for lang in ["golang", "python", "javascript", "kubernetes"]:
        oci_archive(
            name = "semgrep_pro_rules_" + lang,
            image = _GHCR_PREFIX + "/rules-" + lang,
            digest = SEMGREP_PRO_DIGESTS.get("rules_" + lang, ""),
            build_file_content = _RULES_BUILD,
        )

semgrep_pro = module_extension(implementation = _semgrep_pro_impl)
```

**Step 3: Verify syntax**

Run: `bazel build //third_party/semgrep_pro:extensions`
Expected: SUCCESS

**Step 4: Commit**

```bash
git add third_party/semgrep_pro/digests.bzl third_party/semgrep_pro/extensions.bzl
git commit -m "feat: add semgrep pro module extension and digest pins"
```

---

### Task 3: Wire module extension into MODULE.bazel

Register the extension and declare all repos so Bazel can resolve `@semgrep_pro_*` labels.

**Files:**
- Modify: `MODULE.bazel` (insert after the `oci` block, before the `apko` block — around line 205)

**Step 1: Add extension registration**

Insert after line 204 (`use_repo(oci, "gdal_python_base", ...)`):

```starlark
#########################
# Semgrep Pro — engine + per-language rule packs from GHCR
# Digests auto-updated by .github/workflows/update-semgrep-pro.yaml
semgrep_pro = use_extension("//third_party/semgrep_pro:extensions.bzl", "semgrep_pro")
use_repo(
    semgrep_pro,
    "semgrep_pro_engine_amd64",
    "semgrep_pro_engine_arm64",
    "semgrep_pro_rules_golang",
    "semgrep_pro_rules_javascript",
    "semgrep_pro_rules_kubernetes",
    "semgrep_pro_rules_python",
)
```

**Step 2: Verify Bazel resolves the repos**

Run: `bazel query @semgrep_pro_engine_amd64//:all`
Expected: SUCCESS — shows `@semgrep_pro_engine_amd64//:files` (empty filegroup since digests are empty)

Run: `bazel query @semgrep_pro_rules_golang//:all`
Expected: SUCCESS — shows `@semgrep_pro_rules_golang//:files`

**Step 3: Commit**

```bash
git add MODULE.bazel
git commit -m "build: register semgrep pro module extension"
```

---

### Task 4: Create GHA publish workflow

The workflow downloads pro engine + rules, packages them as OCI artifacts, pushes to GHCR, and opens an automerge PR if digests changed.

**Files:**
- Create: `.github/workflows/update-semgrep-pro.yaml`

**Step 1: Write the workflow**

```yaml
# .github/workflows/update-semgrep-pro.yaml
name: Update Semgrep Pro Artifacts

on:
  schedule:
    - cron: "0 6 * * *" # Daily at 06:00 UTC
  workflow_dispatch:
    inputs:
      semgrep_version:
        description: "Semgrep version (leave empty for latest)"
        required: false

concurrency:
  group: update-semgrep-pro
  cancel-in-progress: true

permissions:
  contents: write
  packages: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup crane
        uses: imjasonh/setup-crane@v0.4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Install semgrep
        run: |
          pip install semgrep${{ inputs.semgrep_version && format('=={0}', inputs.semgrep_version) || '' }}
          echo "SEMGREP_VERSION=$(python3 -c 'from semgrep import __VERSION__; print(__VERSION__)')" >> "$GITHUB_ENV"

      - name: Download pro engine (both platforms)
        env:
          SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}
        run: |
          mkdir -p artifacts/engine-amd64 artifacts/engine-arm64

          SEMGREP_URL="https://semgrep.dev"
          AUTH_HEADER="Authorization: Bearer $SEMGREP_APP_TOKEN"

          echo "Downloading pro engine for linux/amd64..."
          curl -sf -H "$AUTH_HEADER" \
            "$SEMGREP_URL/api/agent/deployments/deepbinary/manylinux?version=$SEMGREP_VERSION" \
            -o artifacts/engine-amd64/semgrep-core-proprietary
          chmod 755 artifacts/engine-amd64/semgrep-core-proprietary

          echo "Downloading pro engine for linux/arm64..."
          curl -sf -H "$AUTH_HEADER" \
            "$SEMGREP_URL/api/agent/deployments/deepbinary/linux-arm64?version=$SEMGREP_VERSION" \
            -o artifacts/engine-arm64/semgrep-core-proprietary
          chmod 755 artifacts/engine-arm64/semgrep-core-proprietary

      - name: Download pro rule packs
        env:
          SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}
        run: |
          AUTH_HEADER="Authorization: Bearer $SEMGREP_APP_TOKEN"

          for LANG in golang python javascript kubernetes; do
            echo "Downloading p/$LANG rules..."
            mkdir -p "artifacts/rules-$LANG"
            curl -sf -H "$AUTH_HEADER" \
              "https://semgrep.dev/c/p/$LANG" \
              -o "artifacts/rules-$LANG/$LANG.yaml"
          done

      - name: Package and push OCI artifacts
        run: |
          GHCR_PREFIX="ghcr.io/jomcgi/homelab/tools/semgrep-pro"
          DATE_TAG="$(date +%Y%m%d)"

          declare -A NEW_DIGESTS

          # Push engine artifacts (per-platform)
          for PLATFORM in amd64 arm64; do
            echo "Pushing engine-$PLATFORM..."
            tar -cf "engine-$PLATFORM.tar" -C "artifacts/engine-$PLATFORM" .
            IMAGE="$GHCR_PREFIX/engine-$PLATFORM:$DATE_TAG"
            crane append -f "engine-$PLATFORM.tar" -t "$IMAGE"
            DIGEST=$(crane digest "$IMAGE")
            NEW_DIGESTS["engine_$PLATFORM"]="$DIGEST"
            echo "  engine_$PLATFORM = $DIGEST"
          done

          # Push rule artifacts (per-language)
          for LANG in golang python javascript kubernetes; do
            echo "Pushing rules-$LANG..."
            tar -cf "rules-$LANG.tar" -C "artifacts/rules-$LANG" .
            IMAGE="$GHCR_PREFIX/rules-$LANG:$DATE_TAG"
            crane append -f "rules-$LANG.tar" -t "$IMAGE"
            DIGEST=$(crane digest "$IMAGE")
            NEW_DIGESTS["rules_$LANG"]="$DIGEST"
            echo "  rules_$LANG = $DIGEST"
          done

          # Write digests to env file for next step
          for KEY in "${!NEW_DIGESTS[@]}"; do
            echo "${KEY}=${NEW_DIGESTS[$KEY]}" >> "$GITHUB_ENV"
          done

      - name: Update digests.bzl if changed
        id: update-digests
        run: |
          DIGESTS_FILE="third_party/semgrep_pro/digests.bzl"

          cat > "$DIGESTS_FILE" << 'HEADER'
          """Semgrep Pro OCI artifact digests.

          Updated automatically by .github/workflows/update-semgrep-pro.yaml.
          Do not edit manually — changes will be overwritten.
          """

          SEMGREP_PRO_DIGESTS = {
          HEADER

          # Write each digest (sorted for stable output)
          for KEY in engine_amd64 engine_arm64 rules_golang rules_javascript rules_kubernetes rules_python; do
            VALUE="${!KEY}"
            echo "    \"$KEY\": \"$VALUE\"," >> "$DIGESTS_FILE"
          done

          echo "}" >> "$DIGESTS_FILE"

          # Check for changes
          if git diff --quiet "$DIGESTS_FILE"; then
            echo "No digest changes — nothing to do"
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "Digests changed:"
            git diff "$DIGESTS_FILE"
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Create PR with automerge
        if: steps.update-digests.outputs.changed == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BRANCH="update/semgrep-pro-$(date +%Y%m%d)"

          git checkout -b "$BRANCH"
          git add third_party/semgrep_pro/digests.bzl
          git -c user.name="github-actions[bot]" \
              -c user.email="github-actions[bot]@users.noreply.github.com" \
              commit -m "build(semgrep): update pro artifact digests"

          git push origin "$BRANCH"

          gh pr create \
            --title "build(semgrep): update pro artifact digests" \
            --body "$(cat <<'EOF'
          ## Summary
          - Automated daily update of Semgrep Pro OCI artifact digests
          - Engine version: ${{ env.SEMGREP_VERSION }}
          - Artifacts pushed to ghcr.io/jomcgi/homelab/tools/semgrep-pro/

          🤖 Generated by update-semgrep-pro workflow
          EOF
          )"

          gh pr merge --auto --rebase
```

**Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-semgrep-pro.yaml'))"`
Expected: No errors

**Step 3: Commit**

```bash
git add .github/workflows/update-semgrep-pro.yaml
git commit -m "ci: add daily semgrep pro artifact update workflow"
```

---

### Task 5: Push initial test artifacts and verify Bazel consumption

Manually run the GHA workflow to push initial artifacts, then verify Bazel can pull them.

**Step 1: Push branch and trigger workflow**

```bash
git push -u origin feat/semgrep-pro-oci
```

Then trigger the workflow manually via GitHub UI (Actions > Update Semgrep Pro Artifacts > Run workflow) or via CLI:

```bash
gh workflow run update-semgrep-pro.yaml --ref feat/semgrep-pro-oci
```

**Step 2: Wait for workflow to complete and check output**

```bash
gh run list --workflow=update-semgrep-pro.yaml --limit=1
gh run view <run-id> --log
```

Expected: Workflow pushes 6 artifacts to GHCR and creates a PR updating digests.bzl.

**Step 3: Pull the digest changes locally**

Merge or cherry-pick the digests update, then verify Bazel can pull:

```bash
bazel build @semgrep_pro_engine_amd64//:engine
bazel build @semgrep_pro_rules_golang//:rules
```

Expected: Both succeed — the engine repo contains `semgrep-core-proprietary`, the rules repo contains `golang.yaml`.

**Step 4: Commit any fixes discovered during integration**

---

### Task 6: Update `rules_semgrep` for pro engine support

Add optional pro engine support to the semgrep test macros and shell scripts. Pro rules require NO changes to `rules_semgrep` — they're just YAML filegroups passed via the existing `rules` parameter. The pro engine needs special handling because semgrep looks for `semgrep-core-proprietary` next to `semgrep-core`.

**Files:**
- Modify: `rules_semgrep/test.bzl` (add `pro_engine` parameter)
- Modify: `rules_semgrep/semgrep-test.sh` (add pro engine setup)
- Modify: `rules_semgrep/semgrep-manifest-test.sh` (add pro engine setup)

**Step 1: Write a failing test**

Create a test target that uses the pro engine (this will fail until we implement the feature):

```starlark
# In a temporary BUILD file or existing test BUILD
semgrep_test(
    name = "semgrep_pro_test",
    srcs = glob(["*.go"]),
    rules = ["@semgrep_pro_rules_golang//:rules"],
    pro_engine = "//third_party/semgrep_pro:engine",
)
```

Run: `bazel build //path/to:semgrep_pro_test`
Expected: FAIL — `semgrep_test` doesn't accept `pro_engine` parameter yet.

**Step 2: Update test.bzl — add pro_engine parameter to semgrep_test**

```starlark
def semgrep_test(name, srcs, rules, exclude_rules = [], pro_engine = None, **kwargs):
    """Creates a cacheable test that runs semgrep against source files.

    Args:
        name: Name of the test target
        srcs: Source files to scan (labels)
        rules: Semgrep rule config files or filegroups (labels)
        exclude_rules: List of semgrep rule IDs to skip
        pro_engine: Optional label for semgrep-core-proprietary binary.
            When set, enables --pro flag for deeper analysis.
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)

    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
    ] + rules + srcs

    args = [
        "$(rootpath //tools/semgrep)",
        "$(rootpath //tools/semgrep:pysemgrep)",
    ]

    if pro_engine:
        data.append(pro_engine)
        env["SEMGREP_PRO_ENGINE"] = "$(rootpath {})".format(pro_engine)

    args += ["$(rootpaths {})".format(r) for r in rules]
    args += ["--"]
    args += ["$(rootpaths {})".format(s) for s in srcs]

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = args,
        data = data,
        env = env,
        **kwargs
    )
```

Apply the same pattern to `semgrep_manifest_test` — add `pro_engine` parameter, include in data, set env var.

```starlark
def semgrep_manifest_test(
        name,
        chart,
        chart_files,
        release_name,
        namespace,
        values_files,
        rules = ["//semgrep_rules:kubernetes_rules"],
        exclude_rules = [],
        pro_engine = None,
        **kwargs):
    """Creates a test that renders Helm manifests and scans them with semgrep.

    Args:
        name: Name of the test target
        chart: Path to chart directory
        chart_files: Label for chart's filegroup
        release_name: Helm release name
        namespace: Kubernetes namespace for rendering
        values_files: List of values file labels
        rules: Semgrep rule config files
        exclude_rules: List of semgrep rule IDs to skip
        pro_engine: Optional label for semgrep-core-proprietary binary
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)

    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
        "@multitool//tools/helm",
        chart_files,
    ] + rules + values_files

    if pro_engine:
        data.append(pro_engine)
        env["SEMGREP_PRO_ENGINE"] = "$(rootpath {})".format(pro_engine)

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-manifest-test.sh"],
        args = [
                   "$(rootpath //tools/semgrep)",
                   "$(rootpath //tools/semgrep:pysemgrep)",
                   "$(rootpath @multitool//tools/helm)",
                   release_name,
                   chart,
                   namespace,
               ] + ["$(rootpaths {})".format(r) for r in rules] +
               ["--"] +
               ["$(rootpath {})".format(vf) for vf in values_files],
        data = data,
        env = env,
        **kwargs
    )
```

**Step 3: Update semgrep-test.sh — add pro engine setup**

Insert after line 22 (`export PATH="$(dirname "$PYSEMGREP"):$PATH"`):

```bash
# Set up pro engine if available — semgrep looks for semgrep-core-proprietary
# next to semgrep-core. We use SEMGREP_CORE_BIN to redirect both to a temp dir.
PRO_FLAG=""
if [[ -n "${SEMGREP_PRO_ENGINE:-}" ]]; then
	# Find the bundled semgrep-core binary
	SEMGREP_CORE=$(find . -name "semgrep-core" -not -name "*proprietary*" -type f 2>/dev/null | head -1)
	if [[ -n "$SEMGREP_CORE" ]]; then
		PRO_DIR="${TEST_TMPDIR}/pro_bin"
		mkdir -p "$PRO_DIR"
		cp "$SEMGREP_CORE" "$PRO_DIR/semgrep-core"
		chmod 755 "$PRO_DIR/semgrep-core"
		cp "$SEMGREP_PRO_ENGINE" "$PRO_DIR/semgrep-core-proprietary"
		chmod 755 "$PRO_DIR/semgrep-core-proprietary"
		export SEMGREP_CORE_BIN="$PRO_DIR/semgrep-core"
		PRO_FLAG="--pro-intrafile"
	fi
fi
```

Then update the semgrep invocation on line 56 to include `$PRO_FLAG`:

```bash
if "$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore "$SCAN_DIR"; then
```

Note: Using `--pro-intrafile` instead of `--pro` because our test targets scan individual file sets, not full codebases. `--pro` enables cross-file analysis which requires all source files.

**Step 4: Apply same changes to semgrep-manifest-test.sh**

Same pattern — insert pro engine setup after PATH export (line 27), add `$PRO_FLAG` to semgrep invocation (line 80).

**Step 5: Verify existing tests still pass (no pro engine = no change)**

Run: `bazel test //rules_semgrep/... //tools/semgrep/...`
Expected: All existing tests PASS unchanged (pro_engine defaults to None)

**Step 6: Commit**

```bash
git add rules_semgrep/
git commit -m "feat(semgrep): add optional pro engine support to test rules"
```

---

### Task 7: Wire pro rules into example targets and verify end-to-end

Add pro rules to a few existing `semgrep_test` targets to validate the full pipeline.

**Step 1: Add pro rules to a Go service**

Pick an existing Go service with a `semgrep_test` target (e.g., `tools/oci/BUILD` or `tools/format/BUILD`). Add pro rules:

```starlark
semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.sh"]),
    rules = [
        "//semgrep_rules:shell_rules",
        "@semgrep_pro_rules_golang//:rules",  # Add pro rules
    ],
)
```

**Step 2: Run the test**

Run: `bazel test //tools/oci:semgrep_test`
Expected: PASS (pro rules scan the files, no violations — or violations that need exclude_rules)

**Step 3: Verify cache behavior**

Run: `bazel test //tools/oci:semgrep_test` (again, no changes)
Expected: `(cached)` — Bazel uses the cached result

Change a shell rule (not a pro rule):
Run: `bazel test //tools/oci:semgrep_test`
Expected: Re-runs (shell_rules changed) but pro_rules dependency didn't trigger

**Step 4: Run full test suite**

Run: `bazel test //...`
Expected: All tests pass

**Step 5: Commit and push**

```bash
git add -A
git commit -m "feat(semgrep): wire pro rules into example targets"
git push
```

**Step 6: Create PR**

```bash
gh pr create \
  --title "feat(semgrep): add pro engine and rules via GHCR OCI artifacts" \
  --body "$(cat <<'EOF'
## Summary
- Add `oci_archive` repository rule for fetching OCI artifacts from GHCR
- Add module extension that creates repos for pro engine + per-language rule packs
- Add GHA workflow for daily automated digest updates with automerge
- Add optional pro engine support to `semgrep_test` / `semgrep_manifest_test`

## Design doc
See `docs/plans/2026-03-03-semgrep-pro-oci-design.md`

## Test plan
- [ ] Verify `bazel query @semgrep_pro_engine_amd64//:all` resolves
- [ ] Verify `bazel test //...` passes
- [ ] Trigger update-semgrep-pro workflow manually and verify PR creation
- [ ] Verify digest update PR passes CI

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
