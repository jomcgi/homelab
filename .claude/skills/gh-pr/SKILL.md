---
name: gh-pr
description: Use when creating pull requests, checking PR status, or managing PRs on GitHub. Always verify PR state before sharing links with users.
---

# GitHub CLI - Pull Request Management

## Authentication

The `gh` CLI is authenticated via `GITHUB_TOKEN` environment variable, sourced from 1Password secret `claude.jomcgi.dev`.

## Creating Pull Requests

```bash
# Create PR with title and body
gh pr create --title "feat: add new feature" --body "Description of changes"

# Create draft PR
gh pr create --draft --title "WIP: feature"

# Create PR and open in browser
gh pr create --web
```

## CRITICAL: Always Check PR State

**Before sharing a PR link with the user, ALWAYS verify the PR exists and check its state:**

```bash
# Check if PR exists and get its state
gh pr view --json state,url -q '"\(.state): \(.url)"'
```

Possible states:

- `OPEN` - PR is open and can receive updates
- `MERGED` - PR was merged (don't share as "open")
- `CLOSED` - PR was closed without merging

## Viewing PRs

```bash
# View current branch's PR
gh pr view

# Get PR URL (to share with user)
gh pr view --json url -q .url

# View specific PR by number
gh pr view 123

# View PR with full details
gh pr view --json state,title,url,mergeable,reviews
```

## Checking CI Status

```bash
# Check CI status for current PR
gh pr checks

# Wait for CI to complete
gh pr checks --watch

# Check if PR is mergeable
gh pr view --json mergeable -q .mergeable
```

## Listing PRs

```bash
# List open PRs
gh pr list

# List your PRs
gh pr list --author @me

# List PRs with specific label
gh pr list --label "bug"
```

## Before Pushing Additional Commits

**Always check PR state before pushing:**

```bash
gh pr view --json state -q .state
```

- If `OPEN`: Safe to push more commits
- If `MERGED`: Create a new branch and PR (use `worktree` skill)
- If `CLOSED`: Reopen or create new PR

**Why?** Pushing to a merged branch creates orphaned commits that won't reach main.

## Workflow Summary

1. Make changes in worktree (see `worktree` skill)
2. Commit and push:
   ```bash
   git add .
   git commit -m "Description"
   git push -u origin <branch>
   ```
3. Create PR:
   ```bash
   gh pr create --title "feat: ..." --body "..."
   ```
4. **Verify and share URL:**
   ```bash
   gh pr view --json state,url -q '"\(.state): \(.url)"'
   ```
5. Check CI:
   ```bash
   gh pr checks
   ```

## Tips

- Always verify PR state before sharing links
- Use `--json` flag for scriptable output
- Check CI status after creating PR
- If PR was merged, start fresh with new worktree
