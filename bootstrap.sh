#!/usr/bin/env bash
# Bootstrap developer tools for the homelab repo.
#
# The OCI tools image (ghcr.io/jomcgi/homelab-tools) contains Linux binaries
# for CI use (BuildBuddy remote execution). These cannot run on macOS.
#
# For local macOS development, install tools via Homebrew:
#   brew install crane go node pnpm python gh
#   go install mvdan.cc/gofumpt@latest
#   pnpm install -g prettier
#   pip install ruff
echo "bootstrap.sh is no longer needed for local development."
echo ""
echo "The OCI tools image contains Linux binaries for CI — not macOS."
echo "Install dev tools via Homebrew instead:"
echo "  brew install crane go node pnpm python gh"
echo ""
echo "See CLAUDE.md for the full list of vendored tools."
