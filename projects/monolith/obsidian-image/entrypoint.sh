#!/usr/bin/env bash
set -e

: "${VAULT_NAME:?VAULT_NAME is required}"
: "${OBSIDIAN_EMAIL:?OBSIDIAN_EMAIL is required}"
: "${OBSIDIAN_PASSWORD:?OBSIDIAN_PASSWORD is required}"
: "${VAULT_PATH:=/vault}"

# Wait for the backend to finish git clone (or skip/fail).
# The backend always writes .git-ready, even on failure, so this
# won't block forever.  5-minute timeout as a safety net.
_MAX_WAIT=300
_WAITED=0
while [ ! -f "$VAULT_PATH/.git-ready" ]; do
	if [ "$_WAITED" -ge "$_MAX_WAIT" ]; then
		echo "WARNING: .git-ready not found after ${_MAX_WAIT}s, proceeding anyway"
		break
	fi
	sleep 1
	_WAITED=$((_WAITED + 1))
done

ob login --email "$OBSIDIAN_EMAIL" --password "$OBSIDIAN_PASSWORD"
ob sync-setup --vault "$VAULT_NAME" --path "$VAULT_PATH" --password "$OBSIDIAN_PASSWORD"
cd "$VAULT_PATH"

# Run one-shot sync to completion, then signal readiness before going continuous.
# The readiness probe checks for /tmp/ready so the pod stays not-ready until
# the initial vault download finishes.
ob sync
touch /tmp/ready
exec ob sync --continuous
