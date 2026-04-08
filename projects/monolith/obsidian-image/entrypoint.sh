#!/usr/bin/env bash
set -e

: "${VAULT_NAME:?VAULT_NAME is required}"
: "${OBSIDIAN_EMAIL:?OBSIDIAN_EMAIL is required}"
: "${OBSIDIAN_PASSWORD:?OBSIDIAN_PASSWORD is required}"
: "${VAULT_PATH:=/vault}"

ob login --email "$OBSIDIAN_EMAIL" --password "$OBSIDIAN_PASSWORD"
ob sync-setup --vault "$VAULT_NAME" --path "$VAULT_PATH" --password "$OBSIDIAN_PASSWORD"
cd "$VAULT_PATH"

# Run one-shot sync to completion, then signal readiness before going continuous.
# The readiness probe checks for /tmp/ready so the pod stays not-ready until
# the initial vault download finishes.
ob sync
touch /tmp/ready
exec ob sync --continuous
