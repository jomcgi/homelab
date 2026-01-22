#!/bin/bash
set -e

# npm global directory setup
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"
mkdir -p "$NPM_CONFIG_PREFIX"

# Install/update Claude Code to latest version
# Always run npm install -g to ensure we have the latest version
echo "Installing/updating Claude Code..."
npm install -g @anthropic-ai/claude-code

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

# Install pre-commit to prevent direct commits to main branch
echo "Installing pre-commit hooks..."
pip install --user pre-commit
export PATH="$HOME/.local/bin:$PATH"

# Initialize pre-commit in the repository if it exists
if [ -d "/repos/homelab/.git" ] && [ -f "/repos/homelab/.pre-commit-config.yaml" ]; then
	echo "Setting up pre-commit hooks in /repos/homelab..."
	cd /repos/homelab
	pre-commit install || echo "Warning: Failed to install pre-commit hooks"
	cd - > /dev/null
fi

# Build and start CUI server (new frontend with built-in API)
cd /app/frontend/charts/claude/frontend

# Install dependencies if needed
# We need to temporarily unset NODE_ENV to install devDependencies for building
# Note: Cannot use --ignore-scripts because better-sqlite3 needs to compile native bindings
if [ ! -d "node_modules" ]; then
	echo "Installing CUI server dependencies..."
	NODE_ENV= npm install
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

# Start CUI server with auth disabled (Cloudflare handles SSO)
# --host 0.0.0.0 required for Kubernetes readiness probes (default is localhost)
echo "Starting CUI server..."
exec node dist/server.js --port ${PORT:-3000} --host 0.0.0.0 --skip-auth-token
