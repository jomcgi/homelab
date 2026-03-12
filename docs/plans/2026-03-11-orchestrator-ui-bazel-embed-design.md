# Orchestrator UI: Bazel-Built Embed

## Problem

The orchestrator UI's Vite `dist/` directory is committed to git so that `go:embed` works with both `go build` and Bazel. This adds build artifacts to the repo that must be manually rebuilt and committed on every UI change.

## Decision

Since `go build` compatibility is not required (all builds go through Bazel/CI), wire the `vite_build` output directly into the `go_library`'s `embedsrcs` attribute. This makes Bazel build the UI as a dependency of the Go binary automatically.

## Changes

### 1. `projects/agent_platform/orchestrator/ui/BUILD`

Change `embedsrcs` from `glob(["dist/**"])` to `[":build"]` (the existing `vite_build` target output). This makes the Go library depend on the Vite build through Bazel's dependency graph.

### 2. `.gitignore`

Remove the exception lines that un-ignore `orchestrator/ui/dist/`.

### 3. Delete committed `dist/`

Remove `projects/agent_platform/orchestrator/ui/dist/` from git tracking.

### 4. `projects/agent_platform/orchestrator/ui/static.go`

May need adjustment if the tree artifact structure differs from what `//go:embed dist` expects. Verify after initial build attempt.

## Risk

`rules_go` `embedsrcs` may not handle `js_run_binary`'s tree artifact (directory output) correctly. If so, use the `:build_dist` filegroup or add a `copy_to_directory` intermediary step.

## What doesn't change

- `ui.go` (Go HTTP handler)
- Container image build
- Helm chart / deployment
- Local UI dev workflow (`pnpm dev`)
