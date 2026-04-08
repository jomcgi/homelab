#!/usr/bin/env bash
set -e

: "${VAULT_NAME:?VAULT_NAME is required}"
: "${OBSIDIAN_EMAIL:?OBSIDIAN_EMAIL is required}"
: "${OBSIDIAN_PASSWORD:?OBSIDIAN_PASSWORD is required}"
: "${VAULT_PATH:=/vault}"

ob login --email "$OBSIDIAN_EMAIL" --password "$OBSIDIAN_PASSWORD"
ob sync-setup --vault "$VAULT_NAME" --path "$VAULT_PATH" --password "$OBSIDIAN_PASSWORD"
cd "$VAULT_PATH"
exec ob sync --continuous
