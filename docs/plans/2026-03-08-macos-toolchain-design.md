# macOS Toolchain via OCI Tools Image

**Date:** 2026-03-08
**Status:** Approved

## Problem

The `homelab-tools` OCI image contains Linux (ELF) binaries built from Wolfi packages via apko. On macOS, `crane export` extracts these Linux binaries which cannot execute — they shadow working native tools (`git`, `node`, `go`, etc.) with non-functional binaries. Local development on macOS is broken.

The existing `bazel_env` target in `tools/BUILD` works on macOS (Bazel resolves platform-native binaries), but requires a full Bazel installation and ~45s warm bootstrap.

## Decision

Replace the apko-based tools image with a pure `rules_oci` image built from tar layers. All tool binaries come from `rules_multitool` (which handles multi-platform binary downloads with SHA256 pinning). The OCI image index includes a `darwin/arm64` manifest alongside `linux/amd64` and `linux/arm64`, so `crane export --platform` extracts the correct native binaries on any platform.

## Design

### OCI Image Structure

```
ghcr.io/jomcgi/homelab-tools:main (oci_image_index)
├── linux/amd64   → tar layers (multitool binaries + node + python runtime + pip deps)
├── linux/arm64   → tar layers (multitool binaries + node + python runtime + pip deps)
└── darwin/arm64  → tar layers (multitool binaries + node + python runtime + pip deps)
```

No apko, no Wolfi packages, no apko lock files. Each platform variant is an `oci_image` built from `pkg_tar` layers. Combined into an `oci_image_index` and pushed via `oci_push`.

### Tool Sources

**Standalone binaries via `rules_multitool` (`tools/tools.lock.json`):**

| Tool      | Status                                                               | GitHub releases |
| --------- | -------------------------------------------------------------------- | --------------- |
| helm      | Already in multitool                                                 | Yes             |
| crane     | Already in multitool                                                 | Yes             |
| buildozer | Already in multitool                                                 | Yes             |
| gazelle   | Already in multitool                                                 | Yes             |
| kind      | Already in multitool                                                 | Yes             |
| argocd    | Already in multitool                                                 | Yes             |
| op        | Already in multitool                                                 | Yes             |
| ruff      | **Add**                                                              | astral-sh/ruff  |
| shfmt     | **Add**                                                              | mvdan/sh        |
| gofumpt   | **Add**                                                              | mvdan/gofumpt   |
| gh        | **Add**                                                              | cli/cli         |
| git       | Skip — system-provided on both macOS (Xcode CLT) and Linux (CI host) |

Each entry in `tools.lock.json` has binaries for `linux/amd64`, `linux/arm64`, and `macos/arm64` with pinned SHA256 hashes.

**Node.js via `rules_multitool` or `http_archive`:**

Node.js publishes platform-specific tarballs at `nodejs.org/dist/`. Add to multitool or use a dedicated `http_archive` rule. Prettier is bundled as an npm package alongside Node.

**Python runtime + monorepo deps from Bazel:**

The Python tar layer includes:

1. Python interpreter from `@rules_python` toolchain (platform-specific)
2. Python stdlib
3. All pip packages from `requirements/all.txt` via `@pip//...`

This is a platform-specific `pkg_tar` per variant (`linux/amd64`, `linux/arm64`, `darwin/arm64`).

### Build Targets (`tools/image/BUILD`)

```python
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

# Multitool binaries packaged at /usr/bin/ — one tar per platform
# (implementation: genrule or custom rule that collects multitool binaries
# for the target platform and creates a tar)

pkg_tar(name = "tools_linux_amd64_tar", ...)
pkg_tar(name = "tools_linux_arm64_tar", ...)
pkg_tar(name = "tools_darwin_arm64_tar", ...)

# Node.js + prettier at /usr/bin/node, /usr/bin/prettier
pkg_tar(name = "node_linux_amd64_tar", ...)
pkg_tar(name = "node_linux_arm64_tar", ...)
pkg_tar(name = "node_darwin_arm64_tar", ...)

# Python runtime + stdlib + pip deps
pkg_tar(name = "python_linux_amd64_tar", ...)
pkg_tar(name = "python_linux_arm64_tar", ...)
pkg_tar(name = "python_darwin_arm64_tar", ...)

# Platform-specific images (no base — just layers)
oci_image(
    name = "image_linux_amd64",
    os = "linux",
    architecture = "amd64",
    tars = [
        ":tools_linux_amd64_tar",
        ":node_linux_amd64_tar",
        ":python_linux_amd64_tar",
    ],
)

oci_image(
    name = "image_linux_arm64",
    os = "linux",
    architecture = "arm64",
    tars = [
        ":tools_linux_arm64_tar",
        ":node_linux_arm64_tar",
        ":python_linux_arm64_tar",
    ],
)

oci_image(
    name = "image_darwin_arm64",
    os = "darwin",
    architecture = "arm64",
    tars = [
        ":tools_darwin_arm64_tar",
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

oci_push(
    name = "image.push",
    image = ":image",
    repository = "ghcr.io/jomcgi/homelab-tools",
)
```

### bootstrap.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

TOOLS_IMAGE="ghcr.io/jomcgi/homelab-tools:main"
TOOLS_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/homelab-tools"

# Detect platform
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)   PLATFORM="darwin/arm64" ;;
    Linux-x86_64)   PLATFORM="linux/amd64" ;;
    Linux-aarch64)  PLATFORM="linux/arm64" ;;
    *) echo "ERROR: Unsupported platform: $(uname -s)-$(uname -m)"; exit 1 ;;
esac

# Install crane if missing (macOS only)
if ! command -v crane &>/dev/null; then
    if [[ "$(uname -s)" == "Darwin" ]] && command -v brew &>/dev/null; then
        brew install crane
    else
        echo "ERROR: crane is required. Install from https://github.com/google/go-containerregistry"
        exit 1
    fi
fi

# Check remote digest for this platform
REMOTE_DIGEST=$(crane digest --platform "$PLATFORM" "$TOOLS_IMAGE" 2>/dev/null) || {
    echo "ERROR: Failed to fetch digest for $TOOLS_IMAGE"
    exit 1
}

# Skip if already up to date
if [[ -f "$TOOLS_DIR/.digest" ]] && [[ "$(cat "$TOOLS_DIR/.digest")" == "$REMOTE_DIGEST" ]]; then
    echo "Tools already up to date ($REMOTE_DIGEST)"
    exit 0
fi

echo "Pulling tools for $PLATFORM from $TOOLS_IMAGE..."
rm -rf "$TOOLS_DIR"
mkdir -p "$TOOLS_DIR"
crane export --platform "$PLATFORM" "$TOOLS_IMAGE" - \
    | tar --no-same-owner -xf - -C "$TOOLS_DIR"
echo "$REMOTE_DIGEST" >"$TOOLS_DIR/.digest"
echo "Done. Run 'direnv allow' to add tools to PATH."
```

### .envrc

```bash
export ORION_EXTENSIONS_DIR=$PWD/.aspect/gazelle/

# Developer tools from OCI image (see bootstrap.sh)
TOOLS_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/homelab-tools"
if [[ ! -d "$TOOLS_DIR/usr/bin" ]]; then
    log_error "Run './bootstrap.sh' to install dev tools"
else
    PATH_add "$TOOLS_DIR/usr/bin"
fi
```

### What this replaces

- `tools/image/apko.yaml` — removed (no more Wolfi packages)
- `tools/image/apko.lock.json` — removed
- `homelab_tools_lock` in `MODULE.bazel` — removed
- The `prettier_tar` genrule in `tools/image/BUILD` — replaced by platform-specific node+prettier tar

### What stays the same

- `bazel_env` in `tools/BUILD` — kept as fallback (still useful if someone has Bazel locally)
- `buildbuddy.yaml` CI pipeline — still builds/pushes the image on main
- `rules_multitool` lockfile pattern — extended, not replaced

## Trade-offs

**Gains:**

- macOS dev gets native binaries via `crane export` (~5s)
- Single source of truth for tool versions across all platforms
- No Wolfi package resolution or apko lock management
- Python runtime + deps are identical across local dev and CI

**Costs:**

- More entries in `tools.lock.json` to maintain
- Python packaging is complex (interpreter + stdlib + pip deps in a tar)
- Image size increases (3 platform variants instead of 2)
- No system packages (ca-certs, busybox) — in-cluster agent use case may need a separate base

**Risks:**

- Not all tools may publish standalone macOS binaries (prettier is npm-based)
- Python tar packaging may need custom Bazel rules
- `rules_oci` `oci_image` with `os = "darwin"` may need verification — less common than Linux images

## References

- ADR `architecture/decisions/tooling/001-oci-tool-distribution.md` — parent design
- `docs/plans/2026-03-07-decouple-format-from-bazel-design.md` — formatting subset (updated by this design)
- `tools/tools.lock.json` — existing multitool lockfile
- `tools/image/BUILD` — current image build targets
