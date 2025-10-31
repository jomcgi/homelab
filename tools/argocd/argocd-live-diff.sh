#!/usr/bin/env bash
# tools/argocd/argocd-live-diff.sh
# Fast ArgoCD diff using live server

set -euo pipefail

# Use Bazel-provided binaries if available
ARGOCD_BIN="${ARGOCD:-argocd}"
OP_BIN="${OP:-op}"

# Add common tool locations to PATH for fallback
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Required env vars set by Bazel
APP_NAME="${ARGOCD_APP_NAME:-}"
APP_NAMESPACE="${ARGOCD_APP_NAMESPACE:-}"

if [ -z "$APP_NAME" ]; then
	echo "❌ Error: ARGOCD_APP_NAME not set"
	exit 1
fi

# Get the directory containing application.yaml
# Bazel sets BUILD_WORKSPACE_DIRECTORY to the repo root
REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
	echo "❌ Error: Cannot determine repository root"
	exit 1
fi

# Find the application.yaml directory by searching overlays
APP_DIR=$(find "$REPO_ROOT/overlays" -name "application.yaml" -exec grep -l "name: $APP_NAME" {} \; | head -1 | xargs dirname 2>/dev/null)

if [ -z "$APP_DIR" ]; then
	echo "❌ Error: Cannot find application directory for $APP_NAME"
	exit 1
fi

echo "🔍 ArgoCD Live Diff for: $APP_NAME"
echo "   Directory: ${APP_DIR#$REPO_ROOT/}"
echo ""

# Check if argocd CLI is available
if ! command -v "$ARGOCD_BIN" &>/dev/null; then
	echo "❌ Error: argocd CLI not found"
	exit 1
fi

# Retrieve Cloudflare Access credentials from 1Password if available
HEADER_ARGS=()
if command -v "$OP_BIN" &>/dev/null && "$OP_BIN" account list &>/dev/null; then
	set +e # Don't exit on error for optional credentials
	ACCESS_CLIENT_ID=$("$OP_BIN" read "op://k8s-homelab/argocd-server-auth/ACCESS_CLIENT_ID" 2>/dev/null || echo "")
	ACCESS_CLIENT_SECRET=$("$OP_BIN" read "op://k8s-homelab/argocd-server-auth/ACCESS_CLIENT_SECRET" 2>/dev/null || echo "")
	set -e

	if [ -n "$ACCESS_CLIENT_ID" ] && [ -n "$ACCESS_CLIENT_SECRET" ]; then
		HEADER_ARGS+=(--header "CF-Access-Client-Id: $ACCESS_CLIENT_ID")
		HEADER_ARGS+=(--header "CF-Access-Client-Secret: $ACCESS_CLIENT_SECRET")
		echo "✅ Using Cloudflare Access authentication"
		echo ""
	fi
fi

# Check if logged in to ArgoCD
if ! "$ARGOCD_BIN" app list --grpc-web "${HEADER_ARGS[@]}" &>/dev/null; then
	echo "❌ Error: Not logged in to ArgoCD"
	echo ""
	echo "Login with:"
	echo "  bazel run //tools/argocd:login"
	echo ""
	exit 1
fi

# Run the diff
echo "📊 Running diff against live ArgoCD server..."
echo ""

# The --local flag tells ArgoCD to render from local files instead of fetching from Git
# Pass the application directory which contains application.yaml
# Note: Cloudflare Access headers must be passed for all requests
"$ARGOCD_BIN" app diff "$APP_NAME" \
	--local "$APP_DIR" \
	"${HEADER_ARGS[@]}" || true

echo ""
echo "✅ Diff complete!"
