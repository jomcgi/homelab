#!/bin/bash
set -e

# npm global directory setup
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"
mkdir -p "$NPM_CONFIG_PREFIX"

# Install Claude Code if not already present
if ! command -v claude &>/dev/null; then
	echo "Installing Claude Code..."
	npm install -g @anthropic-ai/claude-code
else
	echo "Claude Code already installed"
fi

# Git configuration
if [ -n "$GIT_USER_NAME" ]; then
	git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
	git config --global user.email "$GIT_USER_EMAIL"
fi
git config --global init.defaultBranch main
git config --global safe.directory '*'

# Git credentials via URL rewrite if token is set
if [ -n "$GITHUB_TOKEN" ]; then
	git config --global url."https://oauth2:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

# Install API server dependencies
cd /app
if [ ! -d "node_modules" ]; then
	echo "Installing API server dependencies..."
	npm install --omit=dev
else
	echo "API server dependencies already installed"
fi

echo "Starting Claude API server..."
exec node /app/dist/index.js
