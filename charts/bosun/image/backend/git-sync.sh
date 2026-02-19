#!/bin/bash
set -e

GOLDEN_PATH="${BOSUN_GOLDEN_PATH:-/repos/golden}"
BRANCH="${REPO_SYNC_BRANCH:-main}"
INTERVAL="${REPO_SYNC_INTERVAL:-60}"

# Build authenticated URL if GITHUB_TOKEN is set
REPO_URL="$REPO_SYNC_URL"
if [ -n "$GITHUB_TOKEN" ]; then
  REPO_URL=$(echo "$REPO_URL" | sed "s|https://|https://x-access-token:${GITHUB_TOKEN}@|")
fi

# Initial clone if not already present
if [ ! -d "$GOLDEN_PATH/.git" ]; then
  echo "git-sync: cloning $REPO_SYNC_URL into $GOLDEN_PATH"
  git clone --branch "$BRANCH" "$REPO_URL" "$GOLDEN_PATH"
fi

# Continuous sync loop
echo "git-sync: syncing $BRANCH every ${INTERVAL}s"
while true; do
  sleep "$INTERVAL"
  cd "$GOLDEN_PATH"
  if ! git fetch origin "$BRANCH" 2>/dev/null; then
    echo "git-sync: fetch failed, retrying next cycle"
    continue
  fi
  if ! git reset --hard "origin/$BRANCH" 2>/dev/null; then
    echo "git-sync: reset failed, attempting recovery"
    git rebase --abort 2>/dev/null || true
    git reset --hard "origin/$BRANCH" 2>/dev/null || echo "git-sync: recovery failed"
  fi
done
