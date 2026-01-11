#!/bin/bash
set -e

# npm global directory setup
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"
mkdir -p "$NPM_CONFIG_PREFIX"

# Install Claude Code if not already present at expected location
CLAUDE_BIN="$NPM_CONFIG_PREFIX/bin/claude"
if [ ! -f "$CLAUDE_BIN" ]; then
	echo "Installing Claude Code..."
	npm install -g @anthropic-ai/claude-code
else
	echo "Claude Code already installed at $CLAUDE_BIN"
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

# Build and start CUI server (new frontend with built-in API)
cd /app/frontend/charts/claude/frontend

# Install dependencies if needed (--ignore-scripts skips husky/prepare hooks)
if [ ! -d "node_modules" ]; then
	echo "Installing CUI server dependencies..."
	npm install --ignore-scripts
else
	echo "CUI server dependencies already installed"
fi

# Build the server and frontend
if [ ! -d "dist" ]; then
	echo "Building CUI server..."
	npm run build
else
	echo "CUI server already built"
fi

# Configure Google API key for voice transcription if set
if [ -n "$GEMINI_API_KEY" ]; then
	export GOOGLE_API_KEY="$GEMINI_API_KEY"
fi

# Start CUI server with auth disabled (Cloudflare handles SSO)
echo "Starting CUI server..."
exec node dist/server.js --port ${PORT:-3000} --skip-auth-token
