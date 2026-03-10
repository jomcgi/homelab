---
name: bazel
description: Use when working with BUILD files, understanding build targets, debugging CI failures, or writing Starlark. Bazel runs remotely via BuildBuddy CI — not locally.
---

# Bazel Build System

## Overview

Bazel is the build system for this repo but runs **remotely via BuildBuddy CI only** — not locally. Developers write BUILD files and push; CI handles building, testing, and pushing images.

Locally, use:

- **`format`** — standalone formatter (no Bazel required), runs as a pre-commit hook
- **`gh pr checks`** — monitor CI results
- **`/buildbuddy`** — debug CI failures via MCP tools

## Local Commands

```bash
format                        # Format code + update BUILD files (standalone)
helm template <release> charts/<chart>/ -f overlays/<env>/<service>/values.yaml  # Render templates
```

`format` runs standalone binaries in parallel:

- Formats Go (gofumpt), Python (ruff), JS/JSON/YAML (prettier), Shell (shfmt), Starlark (buildifier)
- Regenerates push/render BUILD files via grep-based scripts
- Runs gazelle to update BUILD files for Go/Python/Helm

Tools are provided by the OCI tools image via `./bootstrap.sh`.

## What CI Runs

CI is defined in `buildbuddy.yaml` with two parallel actions:

| Action            | What it does                                                 |
| ----------------- | ------------------------------------------------------------ |
| **Format check**  | Runs formatters + gazelle, auto-commits fixes on PR branches |
| **Test and push** | `bazel test //...`, pushes images + deploys pages on main    |

On PR branches, CI auto-commits formatting fixes as `ci-format-bot`. On main, formatting errors fail the build.

## Key Targets (CI-only)

| Target                               | Description               |
| ------------------------------------ | ------------------------- |
| `//charts/<service>/image:image`     | Container image           |
| `//charts/<service>/image:push`      | Push image to registry    |
| `//bazel/images:push_all`            | Push all container images |
| `//projects/websites:push_all_pages` | Deploy all CF Pages sites |
| `//bazel/tools/format:format`        | Format + render all       |

## Writing BUILD Files

BUILD files are still written locally — they define what CI builds.

### Querying Build Graph

```bash
# These still work locally via bb CLI
bazel query //charts/todo/...
bazel query "rdeps(//..., //charts/todo/image:image)"
bazel query "deps(//charts/todo/image:image)"
```

### Gazelle (BUILD File Generation)

Gazelle auto-generates BUILD files for Go, Python, and Helm. Run via:

```bash
format    # Runs gazelle as part of the format pipeline
```

After adding new Go imports or Python dependencies, run `format` to regenerate BUILD files.

## Container Images with apko

For apko.yaml structure, BUILD.bazel patterns, and package reference, see the `container` agent in AGENTS.md.

### Updating Lock Files

```bash
# Update all locks (recommended)
format

# Update a single lock
bazel run @rules_apko//apko -- lock charts/<service>/image/apko.yaml
```

## Debugging CI Failures

Use the `/buildbuddy` skill or MCP tools directly:

1. Get invocation ID: `gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link'`
2. Load tools: `ToolSearch` with `+buildbuddy`
3. Investigate: `buildbuddy-mcp-get-invocation` → `buildbuddy-mcp-get-log` → `buildbuddy-mcp-get-target`

> **Important:** BuildBuddy `get-invocation` requires full 40-char commit SHAs. Always `git rev-parse` short SHAs first.

## Cluster Inspection

Use MCP tools (`ToolSearch` with `+kubernetes`, `+argocd`) — not `//bazel/tools/cluster:*` targets (those wrap kubectl commands blocked by PreToolUse hooks).

## Workflow Integration

Typical workflow after making changes:

1. Edit code or chart files
2. Run `format` to format and render
3. Review changes with `git diff`
4. Commit with conventional commit format and push
5. Create PR via `gh pr create`
6. CI builds, tests, and pushes automatically
