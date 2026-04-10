# Dulwich Vault Git Sync Design

**Goal:** Replace subprocess git calls in the monolith backend with dulwich (pure Python git library), eliminating the system `git` binary dependency. Coordinate startup sequencing with the obsidian sidecar via a sentinel file.

## Architecture

The monolith Python backend handles the vault git lifecycle directly using dulwich. The obsidian sidecar remains for live Obsidian cloud sync but is gated by a sentinel file.

### Startup sequence

1. Python lifespan calls `clone_vault()` → dulwich clones to `/vault`
2. `clone_vault()` writes `/vault/.git-ready` (always, even on failure/skip)
3. Obsidian sidecar sees `.git-ready` → runs `ob login` + `ob sync` + continuous
4. Scheduler starts, reconciler/gardener/backup jobs registered

### Daily backup

`vault_backup_handler()` uses dulwich `porcelain.add`, `porcelain.commit`, `porcelain.push` with token-embedded URL.

## Changes

| File                           | Change                                                                                           |
| ------------------------------ | ------------------------------------------------------------------------------------------------ |
| `pyproject.toml`               | Add `dulwich` dependency                                                                         |
| `knowledge/service.py`         | Rewrite `clone_vault()` and `vault_backup_handler()` to use dulwich, write `.git-ready` sentinel |
| `knowledge/service_test.py`    | Update tests to mock dulwich instead of subprocess                                               |
| `obsidian-image/entrypoint.sh` | Add wait loop for `.git-ready` before `ob sync`                                                  |
| `projects/monolith/BUILD`      | Add `@pip//dulwich` to relevant targets                                                          |

## Error handling

- **Clone failure:** log warning, write `.git-ready` anyway → obsidian sidecar falls back to slow sync
- **Backup failure:** log warning, return None → scheduler retries next cycle
- **Missing `VAULT_GIT_REMOTE`:** skip clone, write `.git-ready` immediately
- **Sidecar timeout:** max wait (5 min) in `entrypoint.sh` so it proceeds even if sentinel never appears

## What we're NOT changing

- Obsidian sidecar container still exists (handles live Obsidian cloud sync)
- Helm chart structure stays the same
- No new images to build
- Readiness probe on sidecar (`/tmp/ready`) unchanged
- `app/main.py` lifespan (already calls `clone_vault()`)
