#!/usr/bin/env bash
# projects/agent_platform/sandboxes/setup-mcp-profiles.sh
#
# Provisions Context Forge teams and scoped JWT tokens for Goose sandbox profiles.
# Stores tokens in 1Password; the 1Password Operator syncs them to Kubernetes.
#
# Prerequisites:
#   - op CLI authenticated (op signin)
#   - python3 with PyJWT installed (pip install pyjwt)
#   - curl, jq
#   - kubectl access to cluster (for port-forward, or use GATEWAY_URL env var)
#
# Usage:
#   ./projects/agent_platform/sandboxes/setup-mcp-profiles.sh
#
# To rotate tokens, re-run the script.
set -euo pipefail

VAULT="k8s-homelab"
OP_ITEM="goose-mcp-tokens"
ADMIN_EMAIL="admin@jomcgi.dev"
TOKEN_TTL_DAYS=30

# Context Forge gateway URL — override with env var or default to port-forward
GATEWAY_URL="${GATEWAY_URL:-}"

cleanup() {
	if [[ -n "${PF_PID:-}" ]]; then
		kill "$PF_PID" 2>/dev/null || true
	fi
}
trap cleanup EXIT

if [[ -z "$GATEWAY_URL" ]]; then
	echo "Starting port-forward to Context Forge..."
	kubectl port-forward -n mcp-gateway svc/context-forge-mcp-stack-mcpgateway 4444:80 &
	PF_PID=$!
	echo "Waiting for gateway to be ready..."
	until curl -sf "http://localhost:4444/health" >/dev/null 2>&1; do
		sleep 2
	done
	GATEWAY_URL="http://localhost:4444"
fi

echo "Using gateway: $GATEWAY_URL"

# Read signing key from 1Password
JWT_SECRET=$(op read "op://${VAULT}/context-forge/JWT_SECRET_KEY")

# Mint a short-lived admin token for API calls
mint_admin_token() {
	JWT_SECRET="$JWT_SECRET" python3 -c "
import jwt, time, uuid, os
payload = {
    'sub': '${ADMIN_EMAIL}',
    'iat': int(time.time()),
    'exp': int(time.time()) + 300,
    'jti': str(uuid.uuid4()),
    'aud': 'mcpgateway-api',
    'iss': 'mcpgateway',
    'is_admin': True,
    'teams': None,
}
print(jwt.encode(payload, os.environ['JWT_SECRET'], algorithm='HS256'))
"
}

# Mint a scoped profile token
mint_profile_token() {
	local sub="$1" teams_json="$2"
	JWT_SECRET="$JWT_SECRET" TEAMS_JSON="$teams_json" python3 -c "
import jwt, time, uuid, json, os
payload = {
    'sub': '${sub}',
    'iat': int(time.time()),
    'exp': int(time.time()) + (${TOKEN_TTL_DAYS} * 86400),
    'jti': str(uuid.uuid4()),
    'aud': 'mcpgateway-api',
    'iss': 'mcpgateway',
    'is_admin': False,
    'teams': json.loads(os.environ['TEAMS_JSON']),
}
print(jwt.encode(payload, os.environ['JWT_SECRET'], algorithm='HS256'))
"
}

ADMIN_TOKEN=$(mint_admin_token)

echo ""
echo "=== Setting up ci-debug profile ==="
echo ""

# Step 1: Create ci-debug team (idempotent)
echo "Creating ci-debug team..."
EXISTING_TEAM=$(curl -sf "${GATEWAY_URL}/teams" \
	-H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[] | select(.name=="ci-debug") | .id // empty' 2>/dev/null || echo "")

if [[ -n "$EXISTING_TEAM" ]]; then
	echo "Team ci-debug already exists: ${EXISTING_TEAM}"
	TEAM_ID="$EXISTING_TEAM"
else
	TEAM_RESPONSE=$(curl -sf -X POST "${GATEWAY_URL}/teams" \
		-H "Authorization: Bearer ${ADMIN_TOKEN}" \
		-H "Content-Type: application/json" \
		-d '{"name": "ci-debug", "description": "BuildBuddy tools for CI debugging"}')
	TEAM_ID=$(echo "$TEAM_RESPONSE" | jq -r '.id')
	if [[ -z "$TEAM_ID" || "$TEAM_ID" == "null" ]]; then
		echo "ERROR: Team creation response did not include an id"
		echo "$TEAM_RESPONSE"
		exit 1
	fi
	echo "Created team ci-debug: ${TEAM_ID}"
fi

# Step 2: Add admin as team member with developer role
echo "Assigning developer role..."
curl -sf -X POST "${GATEWAY_URL}/rbac/users/${ADMIN_EMAIL}/roles" \
	-H "Authorization: Bearer ${ADMIN_TOKEN}" \
	-H "Content-Type: application/json" \
	-d "{\"role_id\": \"developer\", \"scope\": \"team\", \"scope_id\": \"${TEAM_ID}\"}" >/dev/null 2>&1 || true
echo "Role assigned."

# Step 3: Find BuildBuddy tool IDs
echo "Looking up BuildBuddy tools..."
TOOLS_JSON=$(curl -sf "${GATEWAY_URL}/tools?limit=200" \
	-H "Authorization: Bearer ${ADMIN_TOKEN}")
BB_TOOL_IDS=$(echo "$TOOLS_JSON" | jq -r '[.[] | select(.name | startswith("buildbuddy")) | .id] | join(",")')

if [[ -z "$BB_TOOL_IDS" ]]; then
	echo "WARNING: No BuildBuddy tools found. Checking tool names..."
	echo "$TOOLS_JSON" | jq -r '.[].name' | head -20
	echo ""
	echo "You may need to adjust the tool name filter. Searching for tools containing 'build'..."
	BB_TOOL_IDS=$(echo "$TOOLS_JSON" | jq -r '[.[] | select(.name | test("build"; "i")) | .id] | join(",")')
fi

if [[ -z "$BB_TOOL_IDS" ]]; then
	echo "ERROR: No BuildBuddy tools found. Cannot proceed."
	exit 1
fi

echo "BuildBuddy tool IDs: ${BB_TOOL_IDS}"

# Step 4: Set BuildBuddy tools to team visibility
echo "Setting tool visibility to team..."
IFS=',' read -ra TOOL_ARRAY <<<"$BB_TOOL_IDS"
for tool_id in "${TOOL_ARRAY[@]}"; do
	curl -sf -X PUT "${GATEWAY_URL}/tools/${tool_id}" \
		-H "Authorization: Bearer ${ADMIN_TOKEN}" \
		-H "Content-Type: application/json" \
		-d '{"visibility": "team"}' >/dev/null
	echo "  Set tool ${tool_id} to team visibility"
done

# Step 5: Mint scoped JWT for ci-debug
echo ""
echo "Minting ci-debug profile token (${TOKEN_TTL_DAYS}-day TTL)..."
CI_DEBUG_TOKEN=$(mint_profile_token "goose-ci-debug@agents.jomcgi.dev" "[\"${TEAM_ID}\"]")
echo "Token minted."

# Step 6: Store in 1Password
echo ""
echo "Storing token in 1Password (${VAULT}/${OP_ITEM})..."

# Create the item if it doesn't exist, otherwise update it
if op item get "$OP_ITEM" --vault "$VAULT" >/dev/null 2>&1; then
	op item edit "$OP_ITEM" --vault "$VAULT" \
		"CI_DEBUG_MCP_TOKEN=${CI_DEBUG_TOKEN}"
	echo "Updated existing 1Password item."
else
	op item create --category=login --vault "$VAULT" --title "$OP_ITEM" \
		"CI_DEBUG_MCP_TOKEN=${CI_DEBUG_TOKEN}"
	echo "Created new 1Password item."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Wait for 1Password Operator to sync the secret (~30s)"
echo "  2. New sandbox pods will pick up the token automatically"
echo "  3. Test with: agent-run --profile ci-debug 'list recent CI failures'"
echo ""
echo "To rotate tokens, re-run this script."
