---
name: homelab-repo
description: Use when making changes to the homelab repository (charts/, overlays/, operators/, or any infrastructure code). Handles git worktree setup for safe multi-agent workflows. Required for any file modifications in ~/repos/homelab.
---

# Homelab Repository Workflow

## CRITICAL: Read-Only Main Clone

The homelab repo at `~/repos/homelab` is **read-only** (owned by root via git-sync sidecar) and auto-syncs to `origin/main` every 5 minutes. File writes will fail with "Permission denied".

**NEVER commit directly to the `main` branch.**

## Creating a Worktree for Changes

Use the `homelab-worktree` helper to create an isolated working directory:

```bash
# Create a worktree for your feature branch
homelab-worktree feat/add-new-service

# Output:
#   Created worktree: /tmp/homelab-feat-add-new-service
#   Branch: feat/add-new-service (from origin/main)
```

Then work in the worktree:

```bash
cd /tmp/homelab-feat-add-new-service

# Make your changes...
# Commit and push
git add .
git commit -m "Add new service"
git push -u origin feat/add-new-service
```

## Why This Workflow?

1. **Multi-agent safe**: Multiple Claude sessions can work on different branches simultaneously
2. **GitOps compliant**: All changes go through PR review before reaching main
3. **No conflicts**: Each agent gets an isolated `/tmp/` directory
4. **Auto-cleanup**: Worktrees are ephemeral (changes persist via git push)

## Workflow Summary

1. `homelab-worktree <branch-name>` - Create worktree in `/tmp/`
2. `cd /tmp/homelab-<branch>` - Work in the worktree
3. Commit and push to the branch
4. Create PR via GitHub
5. Merge PR - the sync loop pulls changes to `~/repos/homelab` automatically

## Listing and Cleaning Worktrees

```bash
# List all worktrees
git -C ~/repos/homelab worktree list

# Remove a worktree when done (just delete the directory)
rm -rf /tmp/homelab-feat-add-new-service
# The git-sync sidecar will clean up stale worktree references automatically
```
