# Vault Git Sync Design

**Date:** 2026-04-09
**Status:** Approved

## Problem

The monolith's knowledge vault lives on an `emptyDir` volume. On pod restart, the Obsidian headless-sync sidecar re-downloads every file sequentially over its WebSocket protocol — this is slow and has been unreliable (last sync was 2 weeks ago as of writing).

## Solution

Add two git-based features to the monolith Python app:

1. **Startup clone** — `git clone --depth=1` the vault repo before the scheduler starts. Replaces the 5-minute polling loop in `_wait_for_vault_sync()`.
2. **Daily backup job** — A scheduler job that commits and pushes vault changes to GitHub once per day. One pod acquires the lock via `SKIP LOCKED`.

Obsidian headless-sync stays as the live sync source of truth. Git is write-only (no pull) — purely a backup mechanism.

## Architecture

### Startup Flow

```
lifespan starts
  → git clone --depth=1 $VAULT_GIT_REMOTE /vault
  → obsidian headless-sync overwrites with any newer files
  → scheduler starts (reconciler, gardener, vault-backup)
```

### Daily Backup Job

Registered as `knowledge.vault-backup` alongside existing jobs. Handler:

1. Check for uncommitted changes (`git status --porcelain`)
2. If changes exist: `git add -A`, `git commit -m "sync: vault backup"`, `git push`
3. If no changes: no-op

### Credentials

- `GITHUB_TOKEN` from the existing `obsidian` 1Password secret
- Token embedded in clone URL at runtime: `https://x-access-token:{token}@github.com/...`
- Git user config already set via `GIT_CONFIG_*` env vars on the backend container

## File Changes

- `knowledge/service.py` — add `vault_backup_handler()`, `clone_vault()`, register backup job
- `app/main.py` — replace `_wait_for_vault_sync()` with `clone_vault()` call
- `chart/templates/deployment.yaml` — add `VAULT_GIT_REMOTE` and `GITHUB_TOKEN` env vars to backend
- `deploy/values.yaml` — add `gitRemote` under `knowledge`

## Non-Goals

- No `git pull` — Obsidian Sync is the source of truth for file content
- No replacement of the obsidian sidecar — it handles live sync
- No change to the knowledge reconciler or gardener
