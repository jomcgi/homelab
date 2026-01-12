---
name: bazelisk
description: Use when building code, formatting files, rendering manifests, pushing container images, or running tests. Handles all Bazel operations with automatic version management via .bazelversion.
---

# Bazel Build System (bazelisk)

## Overview

Use `bazelisk` for all Bazel commands. It automatically uses the version specified in `.bazelversion` (currently `rolling` = Bazel 9).

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
bazelisk build //...

# Build specific image
bazelisk build //charts/claude/image:image

# Build with verbose output
bazelisk build //charts/claude/image:image --verbose_failures
```

### Pushing Images

```bash
# Push Claude image to registry
bazelisk run //charts/claude/image:push
```

### Running Tests

```bash
# Run all tests
bazelisk test //...

# Run specific test
bazelisk test //pkg/mypackage:mypackage_test

# Run with verbose output
bazelisk test //... --test_output=all
```

### Querying Build Graph

```bash
# List all targets in a package
bazelisk query //charts/claude/...

# Find what depends on a target
bazelisk query "rdeps(//..., //charts/claude/image:image)"

# Show target dependencies
bazelisk query "deps(//charts/claude/image:image)"
```

## Key Targets

| Target | Description |
|--------|-------------|
| `//charts/claude/image:image` | Claude container image |
| `//charts/claude/image:push` | Push Claude image to registry |
| `//tools/format:format` | Format + render all |

## Updating apko Lock Files

When you modify an `apko.yaml` file, update the lock:

```bash
bazelisk run @rules_apko//apko -- lock charts/<service>/image/apko.yaml
```

Or run `format` which updates all locks automatically.

## Caching

Bazel caches build artifacts aggressively:
- Local cache in `~/.cache/bazel`
- Remote cache via BuildBuddy (see build output URLs)

To force rebuild:

```bash
bazelisk build //target --noremote_cache
```

## Troubleshooting

```bash
# Clean build artifacts
bazelisk clean

# Clean everything including external deps
bazelisk clean --expunge

# Show why a target was rebuilt
bazelisk build //target --explain=explain.log --verbose_explanations
```

## Workflow Integration

Typical workflow after making changes:

1. Edit code or chart files
2. Run `format` to format and render
3. Review changes with `git diff`
4. Commit and push via `worktree` skill
5. Create PR via `gh-pr` skill
