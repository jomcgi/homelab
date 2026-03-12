# Orchestrator UI Bazel-Built Embed — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove committed `dist/` from the orchestrator UI by wiring the Bazel `vite_build` output directly into the `go_library` `embedsrcs`.

**Architecture:** The existing `vite_build` macro produces a tree artifact named `dist` via `js_run_binary(out_dirs = ["dist"])`. We change the `go_library` to use this Bazel-built output in `embedsrcs` instead of globbing committed files. The Go `//go:embed dist` directive and `ui.go` handler remain unchanged.

**Tech Stack:** Bazel (rules_go, aspect_rules_js), Go embed, Vite

---

### Task 1: Wire Vite build output into go_library embedsrcs

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/BUILD`

**Step 1: Update the BUILD file**

Change the `go_library` to depend on the Vite build output instead of committed dist files:

```python
# Go library that embeds the Bazel-built Vite output (dist/).
# The vite_build target builds the React dashboard; its tree artifact
# is embedded at compile time via go:embed.
go_library(
    name = "ui",
    srcs = ["static.go"],
    embedsrcs = [":build"],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/orchestrator/ui",
    visibility = ["//projects/agent_platform/orchestrator:__pkg__"],
)
```

Key change: `embedsrcs = glob(["dist/**"])` → `embedsrcs = [":build"]`

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/BUILD
git commit -m "build: wire vite_build output into go_library embedsrcs"
```

---

### Task 2: Remove committed dist/ from git tracking

**Files:**

- Delete from git: `projects/agent_platform/orchestrator/ui/dist/`

**Step 1: Remove dist/ from git tracking (but not from disk yet)**

```bash
git rm -r --cached projects/agent_platform/orchestrator/ui/dist/
```

Note: `--cached` removes from git index only, leaves files on disk (they'll be ignored after the gitignore change).

**Step 2: Commit**

```bash
git commit -m "chore: remove committed orchestrator UI dist/ from git"
```

---

### Task 3: Clean up .gitignore

**Files:**

- Modify: `.gitignore`

**Step 1: Remove the dist/ un-ignore exceptions**

Remove these lines (both old and current paths):

```
# Un-ignore the agent-orchestrator UI dist — committed for go:embed
!services/agent-orchestrator/ui/dist/
!services/agent-orchestrator/ui/dist/**
!projects/agent_platform/orchestrator/ui/dist/
!projects/agent_platform/orchestrator/ui/dist/**
```

Keep the `dist/` global ignore on line 26 — it correctly ignores all dist directories repo-wide.

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: remove dist/ gitignore exceptions for orchestrator UI"
```

---

### Task 4: Push and verify CI

**Step 1: Push the branch**

```bash
git push -u origin feat/bazel-built-ui-embed
```

**Step 2: Create PR**

```bash
gh pr create --title "build: remove committed dist/ from orchestrator UI" --body "$(cat <<'EOF'
## Summary
- Wire `vite_build` Bazel output directly into `go_library` `embedsrcs` instead of globbing committed `dist/` files
- Remove committed `dist/` directory from git tracking
- Clean up `.gitignore` exceptions that were needed for the old approach

The orchestrator UI is now built as a Bazel dependency — no build artifacts in the repo.

## Test plan
- [ ] CI passes (Bazel builds Go binary with embedded Vite output)
- [ ] Verify orchestrator pod starts and serves UI at https://agents.jomcgi.dev/

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Monitor CI**

Use BuildBuddy MCP tools to check the CI build passes, specifically that the `//projects/agent_platform/orchestrator:agent-orchestrator` target compiles with the embedded UI.

**Step 4: If CI fails with embed error**

If `rules_go` can't handle the tree artifact directly, the fallback is to use `:build_dist` filegroup instead of `:build`:

```python
embedsrcs = [":build_dist"],
```

If that also fails, add a `copy_to_directory` rule to flatten the tree artifact into individual files that `embedsrcs` can consume.
