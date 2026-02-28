#!/bin/bash
# PreToolUse hook: blocks git push to branches with closed/merged PRs.
# Prevents Claude from pushing commits to stale PRs.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the push
# Exit 2: block the push (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check git push commands (handles git -C <path> push, git --no-pager push, etc.)
if [[ ! "$COMMAND" =~ git[[:space:]].*push ]] && [[ ! "$COMMAND" =~ ^git[[:space:]]+push ]]; then
	exit 0
fi

# Extract just the "git ... push ..." segment from chained commands.
# e.g. "cd /tmp/foo && git add . && git commit -m x && git push -u origin branch"
# becomes "git push -u origin branch"
PUSH_SEGMENT="$COMMAND"
if [[ "$COMMAND" == *"&&"* ]]; then
	PUSH_SEGMENT=$(echo "$COMMAND" | tr '&' '\n' | grep -E 'git[[:space:]].*push|git[[:space:]]+push' | tail -1 | xargs)
fi

# Extract working directory for git operations.
# Handles: git -C /path push, git push (after cd /path &&), worktree pushes.
# Uses sed for portability (BASH_REMATCH unreliable on macOS bash 5.3+).
GIT_ARGS=()
GIT_DIR=$(echo "$PUSH_SEGMENT" | sed -nE 's/.*-C[[:space:]]+([^[:space:]]+).*/\1/p')
if [ -z "$GIT_DIR" ]; then
	GIT_DIR=$(echo "$COMMAND" | sed -nE 's/.*-C[[:space:]]+([^[:space:]]+).*/\1/p')
fi
if [ -z "$GIT_DIR" ]; then
	GIT_DIR=$(echo "$COMMAND" | sed -nE 's/^cd[[:space:]]+([^[:space:]&]+).*/\1/p')
fi
if [ -n "$GIT_DIR" ]; then
	GIT_ARGS=(-C "$GIT_DIR")
fi

# Determine the branch being pushed.
# Strip the git push prefix and known flags to find [remote] [branch].
# Use [[:space:]] and [^[:space:]] instead of \s and \S for macOS sed compatibility.
PUSH_ARGS=$(echo "$PUSH_SEGMENT" | sed -E 's/^git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(--no-pager[[:space:]]+)?push[[:space:]]*//')
PUSH_ARGS=$(echo "$PUSH_ARGS" | sed -E 's/(-u|--set-upstream|--force|-f|--no-verify|--force-with-lease|--quiet|-q)[[:space:]]*//g')
PUSH_ARGS=$(echo "$PUSH_ARGS" | xargs) # trim whitespace

# Parse remaining args: [remote] [refspec]
read -ra ARGS_ARRAY <<<"$PUSH_ARGS"
BRANCH=""

if [ ${#ARGS_ARRAY[@]} -ge 2 ]; then
	# git push origin branch-name
	BRANCH="${ARGS_ARRAY[1]}"
elif [ ${#ARGS_ARRAY[@]} -le 1 ]; then
	# git push [origin] — branch comes from HEAD
	BRANCH=$(git "${GIT_ARGS[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
fi

# Handle refspec patterns like HEAD:branch or local:remote
if [[ "$BRANCH" == *":"* ]]; then
	BRANCH="${BRANCH##*:}"
	BRANCH="${BRANCH##refs/heads/}"
fi

# Nothing to check if we can't determine the branch
if [ -z "$BRANCH" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "HEAD" ]; then
	exit 0
fi

# Query GitHub for PRs on this branch (all states)
PR_JSON=$(gh pr list --head "$BRANCH" --state all --json state,number,url --jq '.[0]' 2>/dev/null || true)

if [ -z "$PR_JSON" ] || [ "$PR_JSON" = "null" ]; then
	# No PR exists — allow push
	exit 0
fi

STATE=$(echo "$PR_JSON" | jq -r '.state')
PR_NUMBER=$(echo "$PR_JSON" | jq -r '.number')
PR_URL=$(echo "$PR_JSON" | jq -r '.url')

if [ "$STATE" = "CLOSED" ] || [ "$STATE" = "MERGED" ]; then
	cat >&2 <<-EOF
		BLOCKED: PR #${PR_NUMBER} for branch '${BRANCH}' is ${STATE}.
		${PR_URL}

		Pushing to a branch with a ${STATE} PR adds commits that nobody will review.
		Create a new branch and open a fresh PR instead.
	EOF
	exit 2
fi

exit 0
