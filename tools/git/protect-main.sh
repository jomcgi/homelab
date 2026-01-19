#!/bin/bash
# Prevent direct commits to main branch
branch="$(git branch --show-current)"
if [ "$branch" = "main" ]; then
    echo "ERROR: Direct commits to main are not allowed."
    echo "Use a worktree: git worktree add /tmp/claude-worktrees/<name> -b <branch>"
    exit 1
fi
