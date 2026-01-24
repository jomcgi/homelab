---
name: gh-issue
description: Use for autonomous task execution from GitHub Issues. Reads parent issue context, picks a child task, creates worktree, submits PR, merges on CI pass, and closes the issue.
---

# GitHub Issue Task Execution

This skill enables autonomous task execution driven by GitHub Issues. A parent issue provides context and scope; child issues (sub-issues) are atomic tasks to complete.

## Architecture

```
Parent Issue (context + scope)
├── Design doc link (ideas/*.md)
├── Goal description
├── Constraints
└── Sub-issues (atomic tasks)
    ├── Child 1 (open)
    ├── Child 2 (open)
    └── Child 3 (completed)
```

**One agent works one parent at a time.** Locking prevents conflicts.

## Workflow Overview

1. **Acquire lock** on parent issue
2. **Read context** - parent issue + linked design doc
3. **Pick child** - select next workable sub-issue
4. **Execute** - worktree → changes → PR → CI → merge
5. **Close child** - mark sub-issue as done
6. **Check completion** - if all children done, close parent
7. **Release lock** - or continue to next child

## Lock Management

Locks use labels with format: `lock:<agent-id>:<timestamp>`

### Acquire Lock

```bash
AGENT_ID="${CLAUDE_SESSION_ID:-claude-$(date +%s)}"
TIMESTAMP=$(date +%s)
PARENT_ISSUE=42

# Check for existing lock
EXISTING_LOCK=$(gh issue view $PARENT_ISSUE --json labels -q '.labels[].name | select(startswith("lock:"))')

if [ -n "$EXISTING_LOCK" ]; then
    # Parse timestamp from lock
    LOCK_TIME=$(echo "$EXISTING_LOCK" | cut -d: -f3)
    NOW=$(date +%s)
    AGE=$((NOW - LOCK_TIME))

    # TTL is 30 minutes (1800 seconds)
    if [ $AGE -lt 1800 ]; then
        echo "Issue locked by another agent. Skipping."
        exit 1
    fi

    # Stale lock - remove it
    gh issue edit $PARENT_ISSUE --remove-label "$EXISTING_LOCK"
fi

# Acquire lock
gh issue edit $PARENT_ISSUE --add-label "lock:${AGENT_ID}:${TIMESTAMP}"
```

### Release Lock

```bash
# Find and remove our lock
LOCK_LABEL=$(gh issue view $PARENT_ISSUE --json labels -q ".labels[].name | select(startswith(\"lock:${AGENT_ID}:\"))")
gh issue edit $PARENT_ISSUE --remove-label "$LOCK_LABEL"
```

### Refresh Lock (for long-running tasks)

```bash
# Remove old lock, add new timestamp
gh issue edit $PARENT_ISSUE --remove-label "$LOCK_LABEL"
NEW_TIMESTAMP=$(date +%s)
gh issue edit $PARENT_ISSUE --add-label "lock:${AGENT_ID}:${NEW_TIMESTAMP}"
```

## Reading Context

### Get Parent Issue

```bash
PARENT_ISSUE=42

# Get parent issue details
gh issue view $PARENT_ISSUE --json title,body,labels

# Extract design doc link from body (convention: "Design doc: ideas/foo.md")
DESIGN_DOC=$(gh issue view $PARENT_ISSUE --json body -q '.body' | grep -oP 'Design doc: \K\S+')

# Read the design doc if it exists
if [ -n "$DESIGN_DOC" ]; then
    cat ~/repos/homelab/$DESIGN_DOC
fi
```

### List Child Issues

```bash
# Get all sub-issues of parent
gh issue list --parent $PARENT_ISSUE --json number,title,body,state

# Get only open sub-issues
gh issue list --parent $PARENT_ISSUE --state open --json number,title,body
```

## Picking a Child Issue

Let Claude reason about ordering based on context. Read all children, understand dependencies from descriptions, pick the most logical next task.

```bash
# Get open children with full context
CHILDREN=$(gh issue list --parent $PARENT_ISSUE --state open --json number,title,body)

# Claude reads this and decides which to work on based on:
# - Logical dependencies implied in descriptions
# - Complexity (start simple, build up)
# - What's already completed (check closed children)
```

## Executing the Task

Once a child issue is selected, execute using existing skills:

### 1. Create Worktree

```bash
CHILD_ISSUE=43
BRANCH_NAME="issue-${CHILD_ISSUE}"

git -C ~/repos/homelab fetch origin
git -C ~/repos/homelab worktree add -b $BRANCH_NAME /tmp/claude-worktrees/$BRANCH_NAME origin/main
cd /tmp/claude-worktrees/$BRANCH_NAME
```

### 2. Make Changes

Work in the worktree directory. The child issue body should describe what needs to be done.

### 3. Commit and Push

```bash
git add .
git commit -m "$(cat <<'EOF'
fix(component): description of change

Closes #43

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git push -u origin $BRANCH_NAME
```

### 4. Create PR

```bash
gh pr create \
    --title "fix(component): description" \
    --body "$(cat <<'EOF'
## Summary
- What was done

## Related Issues
Closes #43
Parent: #42

## Test Plan
- [ ] CI passes
- [ ] Manual verification

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 5. Wait for CI

```bash
# Wait for checks to complete (with timeout)
gh pr checks --watch --fail-fast

# Or poll with timeout
TIMEOUT=600  # 10 minutes
START=$(date +%s)
while true; do
    STATUS=$(gh pr checks --json state -q '.[].state' | sort -u)
    if [ "$STATUS" = "SUCCESS" ]; then
        echo "CI passed"
        break
    elif echo "$STATUS" | grep -q "FAILURE"; then
        echo "CI failed"
        exit 1
    fi

    NOW=$(date +%s)
    if [ $((NOW - START)) -gt $TIMEOUT ]; then
        echo "CI timeout"
        exit 1
    fi

    sleep 30
done
```

### 6. Merge PR

```bash
# Merge when CI passes
gh pr merge --squash --delete-branch
```

### 7. Close Child Issue

The `Closes #43` in the commit/PR body auto-closes the issue on merge.

Verify:
```bash
gh issue view $CHILD_ISSUE --json state -q .state
# Should be "CLOSED"
```

## Completion Check

After completing a child, check if parent is done:

```bash
# Count remaining open children
OPEN_COUNT=$(gh issue list --parent $PARENT_ISSUE --state open --json number -q 'length')

if [ "$OPEN_COUNT" -eq 0 ]; then
    echo "All children completed. Closing parent."
    gh issue close $PARENT_ISSUE --comment "All sub-issues completed."
else
    echo "$OPEN_COUNT children remaining."
    # Continue to next child or release lock
fi
```

## Error Handling

### CI Failure

```bash
# If CI fails, don't close the issue
# Add a comment and label for human attention
gh issue comment $CHILD_ISSUE --body "CI failed on PR #<pr-number>. Needs investigation."
gh issue edit $CHILD_ISSUE --add-label "needs-attention"

# Release lock so human can investigate
# ... release lock code ...
```

### Blocked Issue

If you determine a child is blocked by something external:

```bash
gh issue edit $CHILD_ISSUE --add-label "blocked"
gh issue comment $CHILD_ISSUE --body "Blocked: <reason>"
# Skip to next child
```

### Lock Refresh

For tasks taking longer than 15 minutes, refresh the lock:

```bash
# In a background loop or periodically during work
refresh_lock() {
    gh issue edit $PARENT_ISSUE --remove-label "$LOCK_LABEL"
    NEW_TIMESTAMP=$(date +%s)
    LOCK_LABEL="lock:${AGENT_ID}:${NEW_TIMESTAMP}"
    gh issue edit $PARENT_ISSUE --add-label "$LOCK_LABEL"
}
```

## Complete Workflow Example

```bash
#!/bin/bash
set -e

PARENT_ISSUE=$1
AGENT_ID="${CLAUDE_SESSION_ID:-claude-$$}"
LOCK_LABEL=""

# Cleanup on exit
cleanup() {
    if [ -n "$LOCK_LABEL" ]; then
        gh issue edit $PARENT_ISSUE --remove-label "$LOCK_LABEL" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# 1. Acquire lock
TIMESTAMP=$(date +%s)
LOCK_LABEL="lock:${AGENT_ID}:${TIMESTAMP}"
gh issue edit $PARENT_ISSUE --add-label "$LOCK_LABEL"

# 2. Read context
echo "=== Parent Issue ==="
gh issue view $PARENT_ISSUE

# 3. Get open children
echo "=== Open Children ==="
CHILDREN=$(gh issue list --parent $PARENT_ISSUE --state open --json number,title,body)
echo "$CHILDREN"

# 4. Claude picks a child and works on it
# ... (interactive Claude work happens here) ...

# 5. Check completion
OPEN_COUNT=$(gh issue list --parent $PARENT_ISSUE --state open --json number -q 'length')
if [ "$OPEN_COUNT" -eq 0 ]; then
    gh issue close $PARENT_ISSUE --comment "All sub-issues completed."
fi

# Lock released by trap
```

## Labels Convention

| Label | Purpose |
|-------|---------|
| `lock:<agent>:<timestamp>` | Indicates active work |
| `agent-ready` | Parent is ready for agent pickup |
| `needs-attention` | Requires human intervention |
| `blocked` | Issue is blocked by external factor |

## Tips

- **Read the full parent context** before picking a child
- **Reason about dependencies** - some tasks logically come before others
- **Refresh lock** during long tasks to prevent timeout
- **Don't force it** - if blocked, label and move on
- **Verify PR state** before any operations (use `gh-pr` skill guidance)
- **Keep commits atomic** - one logical change per child issue
