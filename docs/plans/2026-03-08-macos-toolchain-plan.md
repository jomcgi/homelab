# macOS Toolchain via OCI Tools Image — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a multi-platform OCI tools image using pure `rules_oci` (no apko) with `darwin/arm64` support, so `bootstrap.sh` + `crane export` gives macOS developers native binaries.

**Architecture:** All tool binaries come from `rules_multitool` (multi-platform lockfile). Node.js comes from the Bazel toolchain. Python runtime + pip deps come from `rules_python`. Each platform variant is an `oci_image` with `os`/`architecture` attrs, combined into an `oci_image_index`. `bootstrap.sh` uses `crane export --platform` to extract the right variant.

**Tech Stack:** rules_oci, rules_multitool, rules_pkg, rules_python, rules_nodejs, Bazel bzlmod

**Related:** Design doc `docs/plans/2026-03-08-macos-toolchain-design.md`, ADR `architecture/decisions/tooling/001-oci-tool-distribution.md`

---

### Task 1: Add formatter tools to rules_multitool lockfile

Add `ruff`, `shfmt`, `gofumpt`, and `gh` to `tools/tools.lock.json` with binaries for all three target platforms: `linux/x86_64`, `linux/arm64`, `macos/arm64`.

**Files:**

- Modify: `tools/tools.lock.json`

**Step 1: Look up latest release URLs and SHAs**

For each tool, find the latest release on GitHub and get download URLs + SHA256 checksums for the three platforms. Use `curl -sL <url> | shasum -a 256` to compute checksums.

| Tool    | GitHub repo    | Release asset pattern                                                                             |
| ------- | -------------- | ------------------------------------------------------------------------------------------------- |
| ruff    | astral-sh/ruff | `ruff-<version>-{x86_64-unknown-linux-gnu,aarch64-unknown-linux-gnu,aarch64-apple-darwin}.tar.gz` |
| shfmt   | mvdan/sh       | `shfmt_<version>_{linux,darwin}_{amd64,arm64}` (kind: file)                                       |
| gofumpt | mvdan/gofumpt  | `gofumpt_<version>_{linux,darwin}_{amd64,arm64}` (kind: file)                                     |
| gh      | cli/cli        | `gh_<version>_{linux,macOS}_{amd64,arm64}.tar.gz`                                                 |

**Step 2: Add entries to tools.lock.json**

Follow the existing patterns — `kind: "archive"` for tarballs (ruff, gh), `kind: "file"` for standalone binaries (shfmt, gofumpt). Example for ruff:

```json
"ruff": {
  "binaries": [
    {
      "kind": "archive",
      "url": "https://github.com/astral-sh/ruff/releases/download/<version>/ruff-<version>-x86_64-unknown-linux-gnu.tar.gz",
      "file": "ruff",
      "sha256": "<sha256>",
      "os": "linux",
      "cpu": "x86_64"
    },
    {
      "kind": "archive",
      "url": "https://github.com/astral-sh/ruff/releases/download/<version>/ruff-<version>-aarch64-unknown-linux-gnu.tar.gz",
      "file": "ruff",
      "sha256": "<sha256>",
      "os": "linux",
      "cpu": "arm64"
    },
    {
      "kind": "archive",
      "url": "https://github.com/astral-sh/ruff/releases/download/<version>/ruff-<version>-aarch64-apple-darwin.tar.gz",
      "file": "ruff",
      "sha256": "<sha256>",
      "os": "macos",
      "cpu": "arm64"
    }
  ]
}
```

**Step 3: Verify Bazel can resolve the new tools**

```bash
bazel query @multitool//tools/ruff:all
bazel query @multitool//tools/shfmt:all
bazel query @multitool//tools/gofumpt:all
bazel query @multitool//tools/gh:all
```

Expected: each returns targets including the tool binary.

**Step 4: Commit**

```bash
git add tools/tools.lock.json
git commit -m "build: add ruff, shfmt, gofumpt, gh to rules_multitool lockfile"
```

---

### Task 2: Create multitool tar packaging macro

Create a Bazel macro that takes a list of multitool tool names and packages their binaries into a single `pkg_tar` at `/usr/bin/` for a given platform. This is the core building block for the OCI image layers.

**Files:**

- Create: `tools/image/multitool_tar.bzl`
- Test: verify with `bazel build //tools/image:tools_darwin_arm64_tar`

**Step 1: Understand multitool binary access**

`rules_multitool` exposes each tool at `@multitool//tools/<name>`. The `TOOLS` dict in `@multitool//:tools.bzl` maps tool names to Bazel labels. These labels resolve to the correct platform binary based on the execution platform.

For cross-platform packaging (building darwin binaries on a linux CI host), we need to use Bazel platform transitions. Create platform-specific `genrule` targets that collect binaries and package them.

**Step 2: Create the macro**

Create `tools/image/multitool_tar.bzl`:

```starlark
"""Package multitool binaries into platform-specific tar layers."""

load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@multitool//:tools.bzl", TOOLS = "TOOLS")

def multitool_tar(name, tools, package_dir = "/usr/bin"):
    """Create platform-specific tar layers containing multitool binaries.

    For each platform (linux_amd64, linux_arm64, darwin_arm64), creates a tar
    with all specified tool binaries at package_dir.

    Args:
        name: Base name for generated targets.
        tools: List of tool names from tools.lock.json (e.g., ["ruff", "helm"]).
        package_dir: Directory in the tar for binaries. Default: /usr/bin
    """
    platforms = {
        "linux_amd64": "@rules_go//go/toolchain:linux_amd64",
        "linux_arm64": "@rules_go//go/toolchain:linux_arm64",
        "darwin_arm64": "@rules_go//go/toolchain:darwin_arm64",
    }

    tool_labels = [TOOLS[t] for t in tools]

    for platform_name, platform_label in platforms.items():
        # Transition tool binaries to the target platform
        platform_transition_filegroup(
            name = name + "_srcs_" + platform_name,
            srcs = tool_labels,
            target_platform = platform_label,
        )

        # Package into a tar at /usr/bin/
        native.genrule(
            name = name + "_" + platform_name,
            srcs = [":" + name + "_srcs_" + platform_name],
            outs = [name + "_" + platform_name + ".tar"],
            cmd = """
                set -e
                WORK=$$(mktemp -d)
                mkdir -p "$$WORK{package_dir}"
                for src in $(SRCS); do
                    TOOL_NAME=$$(basename "$$src")
                    cp "$$src" "$$WORK{package_dir}/$$TOOL_NAME"
                    chmod 0755 "$$WORK{package_dir}/$$TOOL_NAME"
                done
                tar -cf $@ -C "$$WORK" .
                rm -rf "$$WORK"
            """.format(package_dir = package_dir),
            visibility = ["//visibility:public"],
        )
```

**Note:** The `platform_transition_filegroup` approach may not work for cross-platform tool selection with `rules_multitool` — multitool uses `select()` on `os` and `cpu` constraints. Verify this works. If not, the fallback is to reference the multitool internal repos directly (e.g., `@multitool_hub.ruff_os_linux_cpu_x86_64//:ruff`) or create separate genrules that use the lockfile URLs directly. **Check the multitool-generated BUILD files to understand the exact target names** before finalizing this macro.

**Step 3: Verify the macro builds**

```bash
bazel build //tools/image:tools_darwin_arm64_tar
bazel build //tools/image:tools_linux_amd64_tar
```

If platform transitions don't work with multitool, investigate the internal repo structure:

```bash
bazel query '@multitool//tools/ruff:all' --output label
```

**Step 4: Commit**

```bash
git add tools/image/multitool_tar.bzl
git commit -m "build: add multitool_tar macro for platform-specific tar packaging"
```

---

### Task 3: Package Node.js + pnpm + prettier per platform

Create platform-specific tar layers containing Node.js, pnpm, and prettier. Node.js comes from the Bazel `@nodejs_*` toolchain repos. Prettier is an npm package that runs on Node.

**Files:**

- Create: `tools/image/node_tar.bzl` (or add genrules directly to `tools/image/BUILD`)

**Step 1: Understand the Node.js toolchain repos**

From `MODULE.bazel` lines 100-112:

```python
use_repo(node, "nodejs_toolchains",
    "nodejs_darwin_amd64", "nodejs_darwin_arm64",
    "nodejs_linux_amd64", "nodejs_linux_arm64",
)
```

Each repo contains a Node.js distribution. Check the structure:

```bash
bazel query '@nodejs_darwin_arm64//:all' --output label
```

The node binary is typically at `@nodejs_<platform>//:node` or `@nodejs_<platform>//:node_bin`.

**Step 2: Create platform-specific node tars**

For each platform, create a genrule that:

1. Copies the node binary to `/usr/bin/node`
2. Copies pnpm (from `@pnpm`) to `/usr/bin/pnpm`
3. Copies the prettier npm package to `/usr/local/lib/node_modules/prettier/`
4. Creates a symlink `/usr/bin/prettier -> ../local/lib/node_modules/prettier/bin/prettier.cjs`

The existing `prettier_tar` genrule in `tools/image/BUILD` shows the pattern for prettier.

**Step 3: Handle pnpm**

pnpm is registered via `use_repo(pnpm, "pnpm")` in MODULE.bazel. Check how to get the binary:

```bash
bazel query '@pnpm//:all' --output label
```

**Step 4: Verify**

```bash
bazel build //tools/image:node_darwin_arm64_tar
bazel build //tools/image:node_linux_amd64_tar
```

Extract and verify:

```bash
tar tf bazel-bin/tools/image/node_darwin_arm64_tar.tar | head -20
```

**Step 5: Commit**

```bash
git add tools/image/
git commit -m "build: add platform-specific Node.js + prettier tar layers"
```

---

### Task 4: Package Python runtime + pip deps per platform

Create platform-specific tar layers containing the Python 3.13 interpreter, stdlib, and all pip dependencies from `requirements/all.txt`.

**Files:**

- Create: `tools/image/python_tar.bzl` (or genrules in BUILD)

**Step 1: Understand the Python toolchain structure**

The Python toolchain is registered via `python.toolchain(python_version = "3.13")` in MODULE.bazel. Check what repos are created:

```bash
bazel query 'deps(@rules_python//python:current_py_toolchain)' 2>/dev/null | head -20
```

Also check the pip repos:

```bash
bazel query '@pip//...' --output label 2>/dev/null | head -20
```

**Step 2: Use py_image_layer for packaging**

The existing `tools/oci/py3_image.bzl` uses `py_image_layer` from `@aspect_rules_py//py:defs.bzl`. This is the right approach — it packages a `py_binary`'s entire dependency tree (interpreter + stdlib + pip wheels) into tar layers.

Create a minimal `py_binary` that imports all the dependencies from `@pip`, then use `py_image_layer` to package it. The binary itself doesn't need to do anything useful — it's just a vehicle for declaring dependencies.

```python
# tools/image/BUILD
load("@aspect_rules_py//py:defs.bzl", "py_venv_binary")

py_venv_binary(
    name = "python_deps",
    srcs = ["python_deps.py"],  # Minimal: just `pass` or imports
    deps = [
        "@pip//aiohttp",
        "@pip//fastapi",
        # ... all deps from requirements/all.txt
    ],
)
```

**Alternative approach:** If `py_image_layer` only works for Linux container images (it may hardcode platform), use a genrule that:

1. Copies the Python toolchain directory
2. Uses `pip install --target` to install wheels
3. Tars the result

This needs investigation. Start with `py_image_layer` and fall back to manual packaging.

**Step 3: Handle platform transitions**

For Linux variants, `py_image_layer` with platform transitions should work (it's the existing pattern in `py3_image.bzl`). For `darwin/arm64`, verify that the Python toolchain has a macOS variant:

```bash
bazel query '@python_3_13_aarch64-apple-darwin//...' 2>/dev/null || echo "No macOS Python toolchain"
```

If no macOS toolchain is registered, add one in MODULE.bazel.

**Step 4: Create per-platform tars**

One tar per platform containing:

- `/usr/bin/python3` → Python interpreter
- `/usr/lib/python3.13/` → stdlib
- `/usr/lib/python3.13/site-packages/` → pip packages

**Step 5: Verify**

```bash
bazel build //tools/image:python_linux_amd64_tar
# Extract and check key paths exist
tar tf bazel-bin/tools/image/python_linux_amd64_tar.tar | grep -E 'python3$|site-packages' | head -10
```

**Step 6: Commit**

```bash
git add tools/image/
git commit -m "build: add platform-specific Python runtime + pip deps tar layers"
```

---

### Task 5: Rewrite tools/image/BUILD for pure rules_oci

Replace the current apko-based image build with pure `rules_oci` — `oci_image` per platform with `os`/`architecture` attrs, combined into `oci_image_index`.

**Files:**

- Modify: `tools/image/BUILD`
- Delete: `tools/image/apko.yaml`
- Delete: `tools/image/apko.lock.json`

**Step 1: Read the current BUILD file**

Current file at `tools/image/BUILD` uses `apko_image()` macro. Replace entirely.

**Step 2: Write the new BUILD file**

```python
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load(":multitool_tar.bzl", "multitool_tar")

# All multitool binaries packaged per platform
multitool_tar(
    name = "tools_tar",
    tools = [
        "argocd",
        "buildozer",
        "crane",
        "gazelle",
        "gh",
        "gofumpt",
        "helm",
        "kind",
        "op",
        "ruff",
        "shfmt",
    ],
)

# Node.js + prettier + pnpm tars (from Task 3)
# ... genrules here ...

# Python runtime + deps tars (from Task 4)
# ... genrules here ...

# Platform-specific images
oci_image(
    name = "image_linux_amd64",
    os = "linux",
    architecture = "amd64",
    tars = [
        ":tools_tar_linux_amd64",
        ":node_linux_amd64_tar",
        ":python_linux_amd64_tar",
    ],
)

oci_image(
    name = "image_linux_arm64",
    os = "linux",
    architecture = "arm64",
    tars = [
        ":tools_tar_linux_arm64",
        ":node_linux_arm64_tar",
        ":python_linux_arm64_tar",
    ],
)

oci_image(
    name = "image_darwin_arm64",
    os = "darwin",
    architecture = "arm64",
    tars = [
        ":tools_tar_darwin_arm64",
        ":node_darwin_arm64_tar",
        ":python_darwin_arm64_tar",
    ],
)

# Multi-platform index
oci_image_index(
    name = "image",
    images = [
        ":image_linux_amd64",
        ":image_linux_arm64",
        ":image_darwin_arm64",
    ],
)

# Push to GHCR
oci_push(
    name = "image.push",
    image = ":image",
    repository = "ghcr.io/jomcgi/homelab-tools",
    # Add stamped tags as in current apko_image macro
)
```

**Step 3: Remove apko artifacts**

```bash
rm tools/image/apko.yaml tools/image/apko.lock.json
```

**Step 4: Update MODULE.bazel**

Remove `homelab_tools_lock` from the `apko.translate_lock` section and `use_repo` call.

**Step 5: Verify the image builds**

```bash
bazel build //tools/image:image
```

**Step 6: Commit**

```bash
git add tools/image/ MODULE.bazel
git commit -m "build: replace apko with pure rules_oci for homelab-tools image"
```

---

### Task 6: Update bootstrap.sh with platform detection

Rewrite `bootstrap.sh` to detect the host OS/arch and pass `--platform` to `crane export`.

**Files:**

- Modify: `bootstrap.sh`

**Step 1: Write the new bootstrap.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

TOOLS_IMAGE="ghcr.io/jomcgi/homelab-tools:main"
TOOLS_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/homelab-tools"

# Detect platform for multi-platform image
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)   PLATFORM="darwin/arm64" ;;
    Linux-x86_64)   PLATFORM="linux/amd64" ;;
    Linux-aarch64)  PLATFORM="linux/arm64" ;;
    *) echo "ERROR: Unsupported platform: $(uname -s)-$(uname -m)"; exit 1 ;;
esac

# Install crane if missing (macOS only — Linux CI should have it)
if ! command -v crane &>/dev/null; then
    if [[ "$(uname -s)" == "Darwin" ]] && command -v brew &>/dev/null; then
        echo "Installing crane via Homebrew..."
        brew install crane
    else
        echo "ERROR: crane is required. Install from https://github.com/google/go-containerregistry"
        exit 1
    fi
fi

# Check remote digest for this platform
REMOTE_DIGEST=$(crane digest --platform "$PLATFORM" "$TOOLS_IMAGE" 2>/dev/null) || {
    echo "ERROR: Failed to fetch digest for $TOOLS_IMAGE ($PLATFORM)"
    echo "Check that the image exists and you have access to ghcr.io"
    exit 1
}

# Skip if already up to date
if [[ -f "$TOOLS_DIR/.digest" ]] && [[ "$(cat "$TOOLS_DIR/.digest")" == "$REMOTE_DIGEST" ]]; then
    echo "Tools already up to date ($REMOTE_DIGEST)"
    exit 0
fi

echo "Pulling developer tools ($PLATFORM) from $TOOLS_IMAGE..."
rm -rf "$TOOLS_DIR"
mkdir -p "$TOOLS_DIR"
crane export --platform "$PLATFORM" "$TOOLS_IMAGE" - \
    | tar --no-same-owner -xf - -C "$TOOLS_DIR"
echo "$REMOTE_DIGEST" >"$TOOLS_DIR/.digest"

echo "Done. Run 'direnv allow' to add tools to PATH."
```

**Step 2: Verify**

```bash
./bootstrap.sh
file "$HOME/.cache/homelab-tools/usr/bin/ruff"
# Expected: Mach-O 64-bit executable arm64 (on macOS)
```

**Step 3: Commit**

```bash
git add bootstrap.sh
git commit -m "fix: add platform detection to bootstrap.sh for multi-platform tools image"
```

---

### Task 7: Re-enable .envrc PATH_add for tools

Update `.envrc` to add the tools directory back to PATH. This reverts the change from the earlier PR that disabled the OCI tools.

**Files:**

- Modify: `.envrc`

**Step 1: Update .envrc**

Replace the comment-only `.envrc` with:

```bash
# For orion gazelle extension
# Note: for direnv, $PWD is always the directory of the .envrc
export ORION_EXTENSIONS_DIR=$PWD/.aspect/gazelle/

# Developer tools from OCI image (see bootstrap.sh)
# Stored in user cache — shared across worktrees, no sudo needed
TOOLS_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/homelab-tools"
if [[ ! -d "$TOOLS_DIR/usr/bin" ]]; then
  log_error "Run './bootstrap.sh' to install dev tools"
else
  PATH_add "$TOOLS_DIR/usr/bin"
  # Check for updates in the background (non-blocking)
  if command -v crane &>/dev/null && [[ -f "$TOOLS_DIR/.digest" ]]; then
    (
      # Detect platform for digest check
      case "$(uname -s)-$(uname -m)" in
        Darwin-arm64)   _PLATFORM="darwin/arm64" ;;
        Linux-x86_64)   _PLATFORM="linux/amd64" ;;
        Linux-aarch64)  _PLATFORM="linux/arm64" ;;
        *)              _PLATFORM="" ;;
      esac
      if [[ -n "$_PLATFORM" ]]; then
        remote=$(crane digest --platform "$_PLATFORM" ghcr.io/jomcgi/homelab-tools:main 2>/dev/null || true)
        local_digest=$(cat "$TOOLS_DIR/.digest")
        if [[ -n "$remote" ]] && [[ "$remote" != "$local_digest" ]]; then
          log_status "Dev tools update available — run './bootstrap.sh'"
        fi
      fi
    ) &
  fi
fi
```

**Step 2: Verify**

```bash
direnv allow
which ruff
which helm
ruff --version
```

**Step 3: Commit**

```bash
git add .envrc
git commit -m "build: re-enable OCI tools PATH in .envrc with platform-aware update check"
```

---

### Task 8: Update bazel_env to use multitool for new tools

Now that ruff, shfmt, gofumpt, and gh are in the multitool lockfile, add them to the `bazel_env` target in `tools/BUILD` so `bazel run //tools:bazel_env` also provides them.

**Files:**

- Modify: `tools/BUILD`

**Step 1: Add new tools to bazel_env**

In the `tools` dict of the `bazel_env` rule, add:

```python
"ruff": MULTITOOL_TOOLS["ruff"],
"shfmt": MULTITOOL_TOOLS["shfmt"],
"gofumpt": MULTITOOL_TOOLS["gofumpt"],
"gh": MULTITOOL_TOOLS["gh"],
```

**Step 2: Verify**

```bash
bazel query //tools:bazel_env --output label
```

**Step 3: Commit**

```bash
git add tools/BUILD
git commit -m "build: add ruff, shfmt, gofumpt, gh to bazel_env"
```

---

### Task 9: Add stamped tags and CI push configuration

Add the stamped tag infrastructure (branch + timestamp tags) to the new `oci_push` target, matching the pattern used by `apko_image` macro.

**Files:**

- Modify: `tools/image/BUILD`

**Step 1: Add expand_template for stamped tags**

Copy the pattern from `tools/oci/apko_image.bzl` lines 166-190:

```python
load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")

expand_template(
    name = "image_stamped_tags_ci",
    out = "image_stamped_ci.tags.txt",
    template = ["{STABLE_BRANCH_TAG}", "{STABLE_IMAGE_TAG}"],
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
)

expand_template(
    name = "image_stamped_tags_local",
    out = "image_stamped_local.tags.txt",
    template = ["{STABLE_IMAGE_TAG}"],
    stamp_substitutions = {
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
)
```

Then update `oci_push` to use them:

```python
oci_push(
    name = "image.push",
    image = ":image",
    repository = "ghcr.io/jomcgi/homelab-tools",
    remote_tags = select({
        "//tools/oci:ci_build": ":image_stamped_tags_ci",
        "//conditions:default": ":image_stamped_tags_local",
    }),
    visibility = ["//images:__pkg__"],
)
```

**Step 2: Verify the push target is queryable**

```bash
bazel query //tools/image:image.push
```

**Step 3: Commit**

```bash
git add tools/image/BUILD
git commit -m "build: add stamped tags and CI push config to tools image"
```

---

### Task 10: End-to-end verification

Verify the full pipeline works: build image → push to GHCR → bootstrap pulls correct platform → tools work.

**Step 1: Build the image locally**

```bash
bazel build //tools/image:image
```

**Step 2: Push to GHCR (or test registry)**

```bash
bazel run //tools/image:image.push
```

Or push to CI by pushing the branch and letting BuildBuddy handle it.

**Step 3: Test bootstrap on macOS**

```bash
rm -rf ~/.cache/homelab-tools
./bootstrap.sh
file ~/.cache/homelab-tools/usr/bin/ruff
# Expected: Mach-O 64-bit executable arm64
```

**Step 4: Verify all tools work**

```bash
ruff --version
shfmt --version
gofumpt -version
helm version --short
crane version
gh --version
node --version
python3 --version
```

**Step 5: Verify pre-commit format hook works**

```bash
echo "" >> README.md
git add README.md
git commit -m "test: verify format hook"
# Should pass — all formatters found
git reset HEAD~1
git checkout README.md
```

**Step 6: Commit any fixups, create PR**

```bash
git push -u origin feat/macos-toolchain
gh pr create --title "feat: multi-platform OCI tools image with macOS support" --body "..."
```
