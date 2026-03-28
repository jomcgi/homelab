#!/bin/sh

VAULT_PATH="${VAULT_PATH:-/vault}"
REMOTE="${GIT_REMOTE}"
BRANCH="${GIT_BRANCH:-main}"
DEBOUNCE="${DEBOUNCE_SECONDS:-10}"
LOCKFILE="$VAULT_PATH/.git/mcp.lock"

cd "$VAULT_PATH"

# Build remote URL with embedded token (more reliable than credential helper)
if [ -n "$REMOTE" ] && [ -n "$GITHUB_TOKEN" ]; then
	TOKEN_REMOTE=$(echo "$REMOTE" | sed "s|https://|https://x-access-token:${GITHUB_TOKEN}@|")
fi

# Initialize git repo if needed
if [ ! -d .git ]; then
	git init -b "$BRANCH"
	# Initial commit of any existing files
	git add -A
	git diff --cached --quiet || git commit -m "sync: initial vault state"
fi

# Ensure correct config on every startup (survives restarts)
git config user.email "vault-sidecar@homelab.local"
git config user.name "vault-sidecar"

# Ensure remote is configured with current token
if [ -n "$TOKEN_REMOTE" ]; then
	if git remote get-url origin >/dev/null 2>&1; then
		git remote set-url origin "$TOKEN_REMOTE"
	else
		git remote add origin "$TOKEN_REMOTE"
	fi
fi

# Ensure we're on the correct branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
	git branch -m "$CURRENT_BRANCH" "$BRANCH"
fi

# Sync with remote if configured
if [ -n "$TOKEN_REMOTE" ]; then
	if git fetch origin "$BRANCH" 2>/dev/null; then
		# Set up tracking and rebase local work on top of remote
		git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" 2>/dev/null
		git rebase "origin/$BRANCH" 2>/dev/null || git rebase --abort 2>/dev/null
	fi
fi

echo "Git sidecar started. Watching $VAULT_PATH for changes..."

while true; do
	sleep "$DEBOUNCE"

	# Skip if MCP server is mid-operation
	if [ -f "$LOCKFILE" ]; then
		continue
	fi

	# Check for uncommitted changes
	if ! git diff --quiet || ! git diff --cached --quiet ||
		[ -n "$(git ls-files --others --exclude-standard)" ]; then
		git add -A
		git commit -m "sync: external changes"

		if [ -n "$TOKEN_REMOTE" ]; then
			if ! git push origin "$BRANCH" 2>&1; then
				echo "Push failed, attempting pull --rebase then push..."
				if git pull --rebase origin "$BRANCH" 2>&1; then
					git push origin "$BRANCH" 2>&1 || echo "Push failed after rebase, will retry next cycle"
				else
					echo "Pull --rebase failed, aborting rebase. Will retry next cycle"
					git rebase --abort 2>/dev/null
				fi
			fi
		fi
	fi
done
