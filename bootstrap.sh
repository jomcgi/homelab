#!/usr/bin/env bash
# Bootstrap developer tools for the homelab repo.
# macOS only — installs crane via Homebrew, then pulls the OCI tools image.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
	echo "ERROR: bootstrap.sh is only supported on macOS."
	echo "For Linux/CI environments, tools are provided via the OCI tools image directly."
	exit 1
fi

# Install crane if missing
if ! command -v crane &>/dev/null; then
	if ! command -v brew &>/dev/null; then
		echo "ERROR: Homebrew is required. Install from https://brew.sh"
		exit 1
	fi
	echo "Installing crane via Homebrew..."
	brew install crane
fi

# Pull tools from OCI image
TOOLS_IMAGE="ghcr.io/jomcgi/homelab-tools:main"
TOOLS_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/homelab-tools"

# Check remote digest
REMOTE_DIGEST=$(crane digest "$TOOLS_IMAGE" 2>/dev/null) || {
	echo "ERROR: Failed to fetch digest for $TOOLS_IMAGE"
	echo "Check that the image exists and you have access to ghcr.io"
	exit 1
}

# Skip if already up to date
if [[ -f "$TOOLS_DIR/.digest" ]] && [[ "$(cat "$TOOLS_DIR/.digest")" == "$REMOTE_DIGEST" ]]; then
	echo "Tools already up to date ($REMOTE_DIGEST)"
	exit 0
fi

echo "Pulling developer tools from $TOOLS_IMAGE..."
rm -rf "$TOOLS_DIR"
mkdir -p "$TOOLS_DIR"
crane export "$TOOLS_IMAGE" - | tar --no-same-owner -xf - -C "$TOOLS_DIR"
echo "$REMOTE_DIGEST" >"$TOOLS_DIR/.digest"

echo "Done. Run 'direnv allow' to add tools to your PATH."
