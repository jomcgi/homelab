---
name: homelab-repo
description: Use when making changes to the homelab repository (charts/, overlays/, operators/, or any infrastructure code). Handles git worktree setup for safe multi-agent workflows. Required for any file modifications in ~/repos/homelab.
---

# Homelab Repository Workflow

## CRITICAL: Read-Only Main Clone

The homelab repo at `~/repos/homelab` is **read-only** (owned by root via git-sync sidecar) and auto-syncs to `origin/main` every 5 minutes. File writes will fail with "Permission denied".

**NEVER commit directly to the `main` branch.**

## Creating a Worktree for Changes

Use git worktree to create an isolated working directory in `/tmp/claude-worktrees/`:

```bash
# Fetch latest from origin
git -C ~/repos/homelab fetch origin

# Create a worktree with a new branch based on origin/main
git -C ~/repos/homelab worktree add -b feat/my-feature /tmp/claude-worktrees/feat-my-feature origin/main
```

Then work in the worktree:

```bash
cd /tmp/claude-worktrees/feat-my-feature

# Make your changes...
# Commit and push
git add .
git commit -m "Add new feature"
git push -u origin feat/my-feature
```

## Why This Workflow?

1. **Multi-agent safe**: Multiple Claude sessions can work on different branches simultaneously
2. **GitOps compliant**: All changes go through PR review before reaching main
3. **No conflicts**: Each agent gets an isolated directory in `/tmp/claude-worktrees/`
4. **Auto-cleanup**: Worktrees are ephemeral (changes persist via git push)

## Workflow Summary

1. Create worktree:
   ```bash
   git -C ~/repos/homelab fetch origin
   git -C ~/repos/homelab worktree add -b <branch-name> /tmp/claude-worktrees/<worktree-name> origin/main
   ```
2. `cd /tmp/claude-worktrees/<worktree-name>` - Work in the worktree
3. Commit and push:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push -u origin <branch-name>
   ```
4. Create PR using gh CLI:
   ```bash
   gh pr create --title "PR title" --body "Description of changes"
   ```
5. **Always share the PR link with the user** after creating or pushing changes:
   ```bash
   gh pr view --json url -q .url
   ```
6. Merge PR - the sync loop pulls changes to `~/repos/homelab` automatically

## Before Pushing Changes

**Always check if your PR has been merged before pushing additional commits:**

```bash
# Check PR status before pushing
gh pr view <branch-name> --json state -q .state
```

- If state is `MERGED`: Your branch was already merged. **Create a new branch and PR** for additional changes.
- If state is `OPEN`: Safe to push additional commits to the existing PR.

**Why?** Pushing to a merged branch creates orphaned commits that won't reach main. You'll need to rebase onto main and create a new PR anyway.

```bash
# If PR was merged, start fresh:
git -C ~/repos/homelab fetch origin
git -C ~/repos/homelab worktree add -b fix/new-issue /tmp/claude-worktrees/new-issue origin/main
```

## Listing and Cleaning Worktrees

```bash
# List all worktrees
git -C ~/repos/homelab worktree list

# Remove a worktree when done (just delete the directory)
rm -rf /tmp/claude-worktrees/<worktree-name>
# The git-sync sidecar will clean up stale worktree references automatically
```
