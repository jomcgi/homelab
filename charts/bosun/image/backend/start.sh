#!/bin/bash
set -e

# npm global directory setup
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$HOME/.local/bin:$NPM_CONFIG_PREFIX/bin:$PATH"
mkdir -p "$NPM_CONFIG_PREFIX"

# Install Claude Code CLI (cached on PVC)
echo "Installing/updating Claude Code (sneakpeek)..."
npm install -g @realmikekelly/claude-sneakpeek

# Git configuration
[ -n "$GIT_USER_NAME" ] && git config --global user.name "$GIT_USER_NAME"
[ -n "$GIT_USER_EMAIL" ] && git config --global user.email "$GIT_USER_EMAIL"
git config --global init.defaultBranch main
git config --global safe.directory '*'

# Configure GitHub CLI as git credential helper
[ -n "$GITHUB_TOKEN" ] && gh auth setup-git

# Start ttyd for terminal access
ttyd -p 7681 -W /bin/bash &

# Start git-sync if repo URL is configured
[ -n "$REPO_SYNC_URL" ] && { /app/git-sync.sh & }

# Wait for golden clone to be ready
if [ -n "$REPO_SYNC_URL" ]; then
  echo "Waiting for golden clone..."
  for i in $(seq 1 120); do
    [ -d "${BOSUN_GOLDEN_PATH:-/repos/golden}/.git" ] && break
    sleep 1
  done
fi

# Start Bosun backend server (Python deps baked into image via py_image_layer)
exec /charts/bosun/backend/server --host 0.0.0.0 --port ${PORT:-8000} --workdir "${DEFAULT_WORKING_DIR:-/home/user}"
