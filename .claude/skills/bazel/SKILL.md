---
name: bazel
description: Use when building code, formatting files, rendering manifests, pushing container images, or running tests. Handles all Bazel operations via BuildBuddy CLI (bb) with automatic version management via .bazelversion.
---

# Bazel Build System (BuildBuddy CLI)

## Overview

This repo uses the **BuildBuddy CLI (`bb`)** as its Bazel launcher. Shell aliases route `bazel` and `bazelisk` to `bb`, so all three commands are interchangeable. The `.bazelversion` file pins BuildBuddy CLI 5.0.321 + Bazel 9.0.0.

The `bb` CLI wraps Bazelisk and adds:
- **Local gRPC proxy** for remote cache/BES — handles retries and buffering transparently
- **`bb login`** for easy BuildBuddy authentication (no manual `--remote_header` needed)
- **Plugin support** for extending the build system

## Common Commands

### Format and Render (Most Common)

```bash
# Format code + render all Helm manifests
format
```

This runs multiple tasks in parallel:

- Updates apko lock files
- Validates apko configs
- Formats Go, Python, JS, Shell code
- Renders all Helm charts to manifests/all.yaml

### Building

```bash
# Build everything
bazel build //...

# Build specific image
bazel build //charts/todo/image:image

# Build with verbose output
bazel build //charts/todo/image:image --verbose_failures
```

### Pushing Images

```bash
# Push Todo image to registry
bazel run //charts/todo/image:push
```

### Running Tests

```bash
# Run all tests
bazel test //...

# Run specific test
bazel test //pkg/mypackage:mypackage_test

# Run with verbose output
bazel test //... --test_output=all
```

### Querying Build Graph

```bash
# List all targets in a package
bazel query //charts/todo/...

# Find what depends on a target
bazel query "rdeps(//..., //charts/todo/image:image)"

# Show target dependencies
bazel query "deps(//charts/todo/image:image)"
```

## Key Targets

| Target                        | Description                    |
| ----------------------------- | ------------------------------ |
| `//charts/todo/image:image` | Todo container image           |
| `//charts/todo/image:push`  | Push Todo image to registry    |
| `//tools/format:format`       | Format + render all            |
| `//tools:help`                | List all available targets     |
| `//tools/cluster:pods`        | List pods in key namespaces    |
| `//tools/cluster:events`      | Recent cluster events          |
| `//tools/cluster:status`      | Cluster health summary         |
| `//tools/cluster:argocd`      | ArgoCD application sync status |

### Cluster Inspection (Read-Only)

Use these targets instead of raw kubectl for common inspection tasks:

```bash
# List pods across key namespaces
bazel run //tools/cluster:pods

# View recent cluster events
bazel run //tools/cluster:events

# Cluster health overview (nodes, resource counts)
bazel run //tools/cluster:status

# ArgoCD sync status for all applications
bazel run //tools/cluster:argocd

# Discover all available targets
bazel run //tools:help
```

## Container Images with apko

For apko.yaml structure, BUILD.bazel patterns, and package reference, see the `container` agent in AGENTS.md.

### Updating Lock Files

```bash
# Update a single lock
bazel run @rules_apko//apko -- lock charts/<service>/image/apko.yaml

# Or update all locks
format
```

## Caching

Bazel caches build artifacts aggressively:

- Local cache in `~/.cache/bazel`
- Remote cache via BuildBuddy (see build output URLs)

To force rebuild:

```bash
bazel build //target --noremote_cache
```

## Troubleshooting

```bash
# Clean build artifacts
bazel clean

# Clean everything including external deps
bazel clean --expunge

# Show why a target was rebuilt
bazel build //target --explain=explain.log --verbose_explanations
```

## Workflow Integration

Typical workflow after making changes:

1. Edit code or chart files
2. Run `format` to format and render
3. Review changes with `git diff`
4. Commit and push via `worktree` skill
5. Create PR via `gh-pr` skill
