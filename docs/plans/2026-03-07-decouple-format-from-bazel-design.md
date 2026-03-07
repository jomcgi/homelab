# Decouple Formatting from Bazel

**Date:** 2026-03-07
**Status:** Draft

## Problem

Local development requires downloading Bazel toolchains (Go SDK, Python interpreter, Node.js) just to run code formatters. The `fast-format.sh` script runs `bazel build` to obtain formatter binaries before executing them, and `bazel run //:gazelle` to regenerate BUILD files. This creates a heavy bootstrap cost for what should be lightweight local operations.

Builds and tests already execute remotely on BuildBuddy — formatting should not require local Bazel infrastructure.

## Decision

Decouple all formatting tools from Bazel by distributing them via the existing OCI tools image (`homelab-tools`). Rewrite `fast-format.sh` to use standalone binaries from `$PATH`. Rewrite generate scripts to use grep/find locally, with `bazel query` validation in CI.

## Design

### 1. OCI Tools Image

Extend `homelab-tools` to include:

| Tool | Version source | Notes |
|------|---------------|-------|
| `ruff` | Pin in apko config | Python formatter/linter |
| `gofumpt` | Pin in apko config | Go formatter |
| `shfmt` | Pin in apko config | Shell formatter |
| `buildifier` | Pin in apko config | Starlark/BUILD formatter |
| `prettier` | Pin in apko config | JS/JSON/YAML/MD formatter — standalone binary, not npm |
| `gazelle` | Pre-built from `//tools:gazelle_binary` | Custom binary with helm/wrangler/semgrep/bzl/go/python extensions |

`bootstrap.sh` already extracts this image into `.tools/bin/` — no changes needed to the extraction path.

**Gazelle special case:** The custom gazelle binary includes repo-specific plugins (rules_helm, rules_wrangler, rules_semgrep). It must be built from source via Bazel. CI builds it and publishes it into the OCI image. When gazelle plugins change, the image is rebuilt.

### 2. Rewrite `fast-format.sh`

Replace the current script that begins with `bazel build ...` with one that:

1. Verifies formatter binaries exist in `$PATH` (exit with helpful error if not)
2. Runs formatters in parallel (same pattern as today):
   - `ruff format .`
   - `find ... | xargs shfmt -w`
   - `find ... | xargs buildifier`
   - `find ... | xargs gofumpt -w`
   - `prettier --write .`
3. Runs rewritten generate scripts in parallel
4. Runs `gazelle` (standalone binary) sequentially at the end

No `bazel build` or `bazel run` calls.

### 3. Rewrite Generate Scripts

Each script gets a grep/find-based implementation for local use:

**`generate-push-all.sh`:**
- Current: `bazel query 'kind("oci_push", //...)'`
- New: `grep -rl 'oci_push(' --include=BUILD .` then parse `name = "..."` from matching rules
- Also grep for `helm_push(` targets

**`generate-push-all-pages.sh`:**
- Current: `bazel query 'kind("wrangler_pages_push", //...)'`
- New: `grep -rl 'wrangler_pages_push(' --include=BUILD .` then parse target names

**`generate-render-all.sh`:**
- Current: `bazel query` with kind+attr intersection
- New: `grep -rl 'name = "render_manifests"' overlays/ --include=BUILD` then construct labels from directory paths

CI validates grep output matches `bazel query` output — if they drift, CI fails with a clear message.

### 4. direnv / .envrc

Replace `bazel_env` PATH with tools image PATH:

```bash
# Before:
# watch_file bazel-out/bazel_env-opt/bin/tools/bazel_env/bin
# PATH_add bazel-out/bazel_env-opt/bin/tools/bazel_env/bin

# After:
TOOLS_DIR="${PWD}/.tools/bin"
if [[ ! -d "$TOOLS_DIR" ]]; then
  log_error "ERROR: Run './bootstrap.sh' to install dev tools"
fi
PATH_add "$TOOLS_DIR"
```

Other tools currently in `bazel_env` (go, python, node, helm, crane, etc.) also move to the OCI image. The `bazel_env` target can be removed entirely if all tools migrate.

### 5. Hook & Skill Rewiring

| Component | File | Change |
|-----------|------|--------|
| Pre-commit `format-code` | `.pre-commit-config.yaml` | No change — still calls `fast-format.sh` |
| Post-rewrite hook | `tools/git/post-rewrite-format.sh` | No change — calls `format` from PATH |
| Claude skill | `.claude/skills/bazel/SKILL.md` | Update: `format` is standalone, remove `//tools/format` references |
| Claude permissions | `.claude/settings.json` | Keep `Bash(format:*)`. Remove stale `bazel run //tools/format` entries |
| CLAUDE.md | `CLAUDE.md` | Update "Essential Commands" — `format` no longer requires Bazel |

### 6. CI Pipeline

`buildbuddy.yaml` format check:

```bash
# Install tools (same OCI image)
./bootstrap.sh

# Run standalone format
./tools/format/fast-format.sh

# Validate generate scripts against bazel query (authoritative check)
./tools/format/validate-generate-scripts.sh  # new script

# Check for drift
git diff --exit-code
```

The new `validate-generate-scripts.sh` runs `bazel query` versions of each generate script and diffs against the grep-based output to ensure consistency.

### 7. Migration Path

1. Build OCI image with all formatter binaries + pre-built gazelle
2. Update `bootstrap.sh` if needed (should work as-is)
3. Rewrite generate scripts with grep/find
4. Rewrite `fast-format.sh` to use standalone binaries
5. Update `.envrc` to use `.tools/bin/`
6. Add CI validation script for generate scripts
7. Update Claude skill, CLAUDE.md, and permissions
8. Remove `bazel_env` format-related entries (or entire target if all tools migrated)

## Trade-offs

**Gains:**
- Zero Bazel dependency for local formatting
- Faster bootstrap (no toolchain downloads)
- `format` works immediately after `./bootstrap.sh`

**Costs:**
- Gazelle binary must be rebuilt when plugins change (CI handles this)
- Generate scripts have two implementations (grep local + bazel query CI)
- Formatter versions managed in apko config rather than Bazel lockfile

**Risks:**
- Grep-based generate scripts could miss targets with unusual patterns → mitigated by CI validation
- Formatter version drift between OCI image and Bazel → eliminated since Bazel no longer provides them
