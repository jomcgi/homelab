#!/usr/bin/env bash
# Test script: Build worker image and create a new TTYD session using the unique tag

set -euo pipefail

SESSION_NAME="${1:-test-session}"
USE_EXISTING="${2:-ask}" # Options: ask, yes, no

echo "===================================="
echo "TTYD Session Manager Test Script"
echo "===================================="
echo ""

# Step 0: Set up port-forward to session manager API
echo "🔌 Step 0: Setting up port-forward to session manager API..."
kubectl port-forward -n ttyd-sessions deployment/ttyd-session-manager 8083:8080 >/dev/null 2>&1 &
API_PF_PID=$!
sleep 3

# Verify port-forward is working
if ! lsof -i :8083 >/dev/null 2>&1; then
	echo "  ✗ Port-forward failed (port 8083 not listening)"
	echo "  Hint: Check if another process is using this port"
	exit 1
fi

echo "  ✓ Port-forward active (PID: ${API_PF_PID})"
echo ""

# Cleanup function to kill port-forward on exit
cleanup_api_pf() {
	if [ ! -z "${API_PF_PID:-}" ]; then
		kill $API_PF_PID 2>/dev/null || true
	fi
}
trap cleanup_api_pf EXIT

# Check for existing sessions
echo "🔍 Checking for existing sessions..."
SESSIONS_RESPONSE=$(curl -s http://localhost:8083/api/sessions || echo '[]')
SESSIONS_COUNT=$(echo "$SESSIONS_RESPONSE" | jq -r 'length')

if [ "$SESSIONS_COUNT" -gt 0 ]; then
	echo "  Found $SESSIONS_COUNT existing session(s):"
	echo "$SESSIONS_RESPONSE" | jq -r '.[] | "    - \(.id) (\(.name)) - \(.state) - Created: \(.created_at // "unknown")"'
	echo ""

	if [ "$USE_EXISTING" = "ask" ]; then
		read -p "Use most recent session? (y/n): " -n 1 -r
		echo
		if [[ $REPLY =~ ^[Yy]$ ]]; then
			USE_EXISTING="yes"
		else
			USE_EXISTING="no"
		fi
	fi

	if [ "$USE_EXISTING" = "yes" ]; then
		# Get the most recent session (first in the list)
		SESSION_ID=$(echo "$SESSIONS_RESPONSE" | jq -r '.[0].id')
		SESSION_NAME=$(echo "$SESSIONS_RESPONSE" | jq -r '.[0].name')
		echo "  ✓ Using existing session: $SESSION_ID ($SESSION_NAME)"
		echo ""

		# Skip to displaying the URL
		SKIP_BUILD=true
	fi
else
	echo "  No existing sessions found"
	echo ""
fi

# Step 1: Build the worker image (unless using existing session)
if [ "${SKIP_BUILD:-false}" = "true" ]; then
	echo "⏭️  Skipping build steps (using existing session)"
	echo ""
else
	echo "🔨 Step 1: Building worker image..."
	echo "  Building: //charts/ttyd-session-manager/backend:ttyd_worker_image"
	format
	bazel build --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image
	echo "  ✓ Build complete"
	echo ""

	# Step 2: Push the image and capture the actual tag
	echo "📤 Step 2: Pushing worker image to registry..."
	PUSH_OUTPUT=$(bazel run --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image.push 2>&1)
	echo "$PUSH_OUTPUT"

	# Extract the tag from the push output
	# Format: ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:TAG: digest: ...
	IMAGE_TAG=$(echo "$PUSH_OUTPUT" | grep -oE 'ttyd-worker:[^ :]+' | cut -d: -f2 | head -1)

	if [ -z "$IMAGE_TAG" ]; then
		echo "  ✗ Failed to extract image tag from push output"
		exit 1
	fi

	echo ""
	echo "  ✓ Image pushed successfully with tag: ${IMAGE_TAG}"
	echo ""

	# Step 3: Create session with the unique image tag
	echo "🚀 Step 3: Creating session with image tag ${IMAGE_TAG}..."
	SESSION_RESPONSE=$(curl -X POST http://localhost:8083/api/sessions \
		-H "Content-Type: application/json" \
		-d "{\"display_name\": \"${SESSION_NAME}\", \"image_tag\": \"${IMAGE_TAG}\"}" -s)

	echo "  API Response:"
	echo "$SESSION_RESPONSE" | jq .

	SESSION_ID=$(echo "$SESSION_RESPONSE" | jq -r '.id')
	POD_NAME="ttyd-session-${SESSION_ID}"

	if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
		echo "  ✗ Failed to create session"
		exit 1
	fi

	echo "  ✓ Session created successfully"
	echo "    - Session ID: ${SESSION_ID}"
	echo "    - Pod Name: ${POD_NAME}"
	echo "    - Image Tag: ${IMAGE_TAG}"
	echo ""

	# Step 4: Wait for pod to be ready
	echo "⏳ Step 4: Waiting for pod to be ready..."
	kubectl wait --for=condition=ready pod/$POD_NAME -n ttyd-sessions --timeout=120s
	echo "  ✓ Pod is ready"
	echo ""
fi

# Final step: Display the terminal URL
echo "===================================="
echo "✅ Success! Terminal ready at:"
echo "   https://test.jomcgi.dev/sessions/${SESSION_ID}"
echo "===================================="
echo ""
echo "Session Details:"
echo "  - Session ID: ${SESSION_ID}"
echo "  - Session Name: ${SESSION_NAME}"
echo "  - Pod Name: ttyd-session-${SESSION_ID}"
echo ""
echo "Note: The session will remain running in the cluster."
echo "To delete it later, run:"
echo "  kubectl delete pod ttyd-session-${SESSION_ID} -n ttyd-sessions"
echo ""
