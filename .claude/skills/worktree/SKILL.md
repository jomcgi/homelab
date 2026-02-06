---
name: worktree
description: Use when making changes to the homelab repository (charts/, overlays/, operators/, or any infrastructure code). Handles git worktree setup for safe multi-agent workflows. Required for any file modifications in ~/repos/homelab.
---

# Homelab Repository Worktree Workflow

## Repository Structure

**WARNING: The main repo at `~/repos/homelab` has an auto-fetch loop running every 60 seconds (`git fetch origin`).** This can cause conflicts if you're working directly in that directory. Always use worktrees in `/tmp/claude-worktrees/` for active development to avoid these conflicts.

The homelab repo at `~/repos/homelab` is a writable clone that auto-fetches from `origin/main` every 60 seconds. While you CAN write to this directory, you should use git worktrees for feature branches to enable multi-agent workflows.

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
4. **Persistent repo**: The main clone persists on PVC, only worktrees are ephemeral
5. **Auto-sync**: The sync loop runs `git fetch origin` every 60s to keep refs fresh

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
4. Create PR using the `gh-pr` skill
5. Merge PR - the sync loop will fetch the changes automatically

## Listing and Cleaning Worktrees

```bash
# List all worktrees
git -C ~/repos/homelab worktree list

# Remove a worktree when done (just delete the directory)
rm -rf /tmp/claude-worktrees/<worktree-name>

# Clean up stale worktree references
git -C ~/repos/homelab worktree prune
```

## Starting Fresh After PR Merge

If your PR was merged and you need to make more changes:

```bash
git -C ~/repos/homelab fetch origin
git -C ~/repos/homelab worktree add -b fix/new-issue /tmp/claude-worktrees/new-issue origin/main
```

## Working Directly in Main Clone (Not Recommended)

While you can work directly in `~/repos/homelab`, this is NOT recommended because:

- The sync loop runs `git fetch` every 60s which could conflict with your work
- Multiple Claude sessions would conflict with each other
- Direct commits to main bypass PR review

If you must work directly:

```bash
cd ~/repos/homelab
git checkout -b feat/my-feature origin/main
# Make changes, commit, push, create PR
git checkout main  # Return to main when done
```
