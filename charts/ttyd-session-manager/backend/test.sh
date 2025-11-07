#!/usr/bin/env bash
# Test script: Build worker image and create a new TTYD session using the unique tag

set -euo pipefail

SESSION_NAME="${1:-test-session}"

echo "===================================="
echo "TTYD Session Manager Test Script"
echo "===================================="
echo ""

# Step 1: Build the worker image
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

# Step 3: Set up port-forward to session manager
echo "🔌 Step 3: Setting up port-forward to session manager..."
kubectl port-forward -n ttyd-sessions deployment/ttyd-session-manager 8083:8080 >/dev/null 2>&1 &
PF_PID=$!
sleep 3

# Verify port-forward is working
if ! lsof -i :8083 >/dev/null 2>&1; then
	echo "  ✗ Port-forward failed (port 8083 not listening)"
	echo "  Hint: Check if another process is using this port"
	exit 1
fi

echo "  ✓ Port-forward active (PID: ${PF_PID})"
echo ""

# Cleanup function to kill port-forward and delete session on exit
cleanup() {
	echo ""
	echo "🧹 Cleaning up..."

	# Kill port-forward if it exists
	if [ ! -z "${PF_PID:-}" ]; then
		kill $PF_PID 2>/dev/null || true
		echo "  ✓ Port-forward stopped"
	fi

	# Delete the session pod if it was created
	if [ ! -z "${SESSION_ID:-}" ]; then
		echo "  Deleting session pod: ttyd-session-${SESSION_ID}"
		kubectl delete pod ttyd-session-${SESSION_ID} -n ttyd-sessions --ignore-not-found=true 2>/dev/null || true
		echo "  ✓ Session pod deleted"
	fi
}
trap cleanup EXIT

# Step 4: Create session with the unique image tag
echo "🚀 Step 4: Creating session with image tag ${IMAGE_TAG}..."
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

# Kill manager port-forward (we'll create a new one for the session)
kill $PF_PID 2>/dev/null || true
PF_PID="" # Clear PF_PID so cleanup doesn't try to kill it again

# Step 5: Wait for pod to be ready
echo "⏳ Step 5: Waiting for pod to be ready..."
kubectl wait --for=condition=ready pod/$POD_NAME -n ttyd-sessions --timeout=120s
echo "  ✓ Pod is ready"
echo ""

# Step 6: Port-forward to the session
echo "🌐 Step 6: Port-forwarding to session terminal..."
echo ""
echo "===================================="
echo "✅ Success! Terminal ready at:"
echo "   http://localhost:7681"
echo "===================================="
echo ""
echo "Press Ctrl+C to stop port-forward and exit"
echo ""

kubectl port-forward -n ttyd-sessions $POD_NAME 7681:7681
