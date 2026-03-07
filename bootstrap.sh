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
TOOLS_IMAGE="ghcr.io/jomcgi/homelab-tools:latest"
TOOLS_DIR="$PWD/.tools"

echo "Pulling developer tools from $TOOLS_IMAGE..."
mkdir -p "$TOOLS_DIR/bin"
crane export "$TOOLS_IMAGE" - | tar -xf - -C "$TOOLS_DIR" --strip-components=1 tools/
touch "$TOOLS_DIR/.pulled"

echo "Done. Run 'direnv allow' to add tools to your PATH."
