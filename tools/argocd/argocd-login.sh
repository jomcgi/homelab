#!/usr/bin/env bash
# tools/argocd/argocd-login.sh
# Authenticate to ArgoCD using credentials from 1Password

set -euo pipefail

# Use Bazel-provided binaries if available
ARGOCD_BIN="${ARGOCD:-argocd}"
OP_BIN="${OP:-op}"

# ArgoCD server details
ARGOCD_SERVER="${ARGOCD_SERVER:-argocd.jomcgi.dev}"
ONEPASSWORD_ITEM="${ONEPASSWORD_ITEM:-op://k8s-homelab/argocd-server-auth}"

echo "🔐 ArgoCD Login via 1Password"
echo ""

# Check if op CLI is available
if ! command -v "$OP_BIN" &>/dev/null; then
	echo "❌ Error: 1Password CLI (op) not found"
	echo ""
	echo "Bazel will download it automatically on first use."
	exit 1
fi

# Check if logged into 1Password
if ! "$OP_BIN" account list &>/dev/null; then
	echo "❌ Error: Not logged into 1Password"
	echo ""
	echo "Login with:"
	echo "  $OP_BIN signin"
	echo ""
	echo "This is the ONLY authentication you need!"
	echo "All other credentials will be retrieved from 1Password."
	exit 1
fi

echo "✅ Logged into 1Password"
echo ""

# Retrieve credentials from 1Password
echo "🔍 Retrieving ArgoCD credentials from 1Password..."
echo "   Using op binary: $OP_BIN"
echo "   Item: $ONEPASSWORD_ITEM"

# Get credentials using op CLI
# Note: 2>/dev/null suppresses errors for optional fields
set +e # Don't exit on error for optional fields
USERNAME=$("$OP_BIN" read "${ONEPASSWORD_ITEM}/USERNAME" 2>&1 || echo "")
PASSWORD=$("$OP_BIN" read "${ONEPASSWORD_ITEM}/PASSWORD" 2>&1 || echo "")
ACCESS_CLIENT_ID=$("$OP_BIN" read "${ONEPASSWORD_ITEM}/ACCESS_CLIENT_ID" 2>&1 || echo "")
ACCESS_CLIENT_SECRET=$("$OP_BIN" read "${ONEPASSWORD_ITEM}/ACCESS_CLIENT_SECRET" 2>&1 || echo "")
set -e # Re-enable exit on error

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
	echo "❌ Error: Could not retrieve credentials from 1Password"
	echo ""
	echo "Expected item: $ONEPASSWORD_ITEM"
	echo "Required fields: USERNAME, PASSWORD"
	echo "Optional fields: ACCESS_CLIENT_ID, ACCESS_CLIENT_SECRET (for Cloudflare Access)"
	exit 1
fi

echo "✅ Retrieved credentials from 1Password"
echo ""

# Login to ArgoCD
echo "🔑 Authenticating to ArgoCD ($ARGOCD_SERVER)..."

# Build login command with Cloudflare Access headers if available
LOGIN_ARGS=(
	"$ARGOCD_SERVER"
	--username "$USERNAME"
	--password "$PASSWORD"
	--grpc-web
)

if [ -n "$ACCESS_CLIENT_ID" ] && [ -n "$ACCESS_CLIENT_SECRET" ]; then
	echo "   Using Cloudflare Access for authentication"
	LOGIN_ARGS+=(--header "CF-Access-Client-Id: $ACCESS_CLIENT_ID")
	LOGIN_ARGS+=(--header "CF-Access-Client-Secret: $ACCESS_CLIENT_SECRET")
fi

echo ""

# Login to ArgoCD
# Note: Cloudflare Access tokens must be passed as HTTP headers
# Note: v2.13.2 doesn't support --password-stdin, so password is passed via flag
if "$ARGOCD_BIN" login "${LOGIN_ARGS[@]}"; then
	echo ""
	echo "✅ Successfully logged into ArgoCD!"
	echo ""
	echo "Credentials cached in: ~/.config/argocd/config"
	echo ""
	echo "Now you can run diffs:"
	echo "  bazel run //overlays/prod/n8n:diff"
else
	echo ""
	echo "❌ Failed to login to ArgoCD"
	echo ""
	echo "Check:"
	echo "  1. ArgoCD server is accessible: curl https://$ARGOCD_SERVER"
	echo "  2. Cloudflare Access tokens are valid (if using)"
	echo "  3. Username/password are correct in 1Password"
	exit 1
fi
