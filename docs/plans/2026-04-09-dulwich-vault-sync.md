# Dulwich Vault Git Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace subprocess git calls with dulwich (pure Python) and gate the obsidian sidecar behind a `.git-ready` sentinel file so the git clone completes before obsidian starts syncing.

**Architecture:** `clone_vault()` uses `dulwich.porcelain.clone(depth=1)` to pre-seed the vault emptyDir, then writes `/vault/.git-ready`. The obsidian sidecar waits for that sentinel before running `ob sync`. `vault_backup_handler()` uses dulwich porcelain for add/commit/push. All subprocess git calls are removed.

**Tech Stack:** Python, dulwich, Helm, bash

---

### Task 1: Add dulwich as a runtime dependency

**Files:**

- Modify: `pyproject.toml:74-85` (add dulwich to dependencies list)
- Modify: `projects/monolith/BUILD:64-82` (add `@pip//dulwich` to `monolith_backend` deps)

**Step 1: Add dulwich to pyproject.toml**

In `pyproject.toml`, add `dulwich` to the `dependencies` list, after the existing monolith dependencies block:

```python
    # Knowledge vault git sync
    "dulwich",
```

**Step 2: Add `@pip//dulwich` to the monolith_backend py_library**

In `projects/monolith/BUILD`, add to the `monolith_backend` deps list (line ~65, alphabetical order):

```python
        "@pip//dulwich",
```

**Step 3: Regenerate requirements lockfiles**

Run: `bb remote run //bazel/requirements:update --config=ci`

If that doesn't work (the update target may need local uv), run locally:

```bash
cd /tmp/claude-worktrees/dulwich-vault-sync
uv pip compile pyproject.toml -o bazel/requirements/runtime.txt
uv pip compile bazel/requirements/all.in -o bazel/requirements/all.txt -c bazel/requirements/runtime.txt
```

**Step 4: Commit**

```bash
git add pyproject.toml bazel/requirements/runtime.txt bazel/requirements/all.txt projects/monolith/BUILD
git commit -m "build(monolith): add dulwich pure-python git dependency"
```

---

### Task 2: Rewrite `clone_vault()` to use dulwich

**Files:**

- Modify: `projects/monolith/knowledge/service.py:1-59`
- Modify: `projects/monolith/knowledge/service_test.py:261-312`

**Step 1: Write the failing tests**

Replace the entire `TestCloneVault` class in `service_test.py` (lines 261-312) with:

```python
class TestCloneVault:
    _SENTINEL = ".git-ready"

    @pytest.mark.asyncio
    async def test_skips_when_git_remote_unset(self, monkeypatch, tmp_path, caplog):
        """clone_vault writes sentinel and returns when VAULT_GIT_REMOTE is empty."""
        monkeypatch.delenv("VAULT_GIT_REMOTE", raising=False)
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with caplog.at_level(logging.INFO, logger="knowledge.service"):
            await service.clone_vault()
        assert any("VAULT_GIT_REMOTE not set" in r.message for r in caplog.records)
        assert (tmp_path / self._SENTINEL).exists()

    @pytest.mark.asyncio
    async def test_skips_when_already_cloned(self, monkeypatch, tmp_path, caplog):
        """clone_vault skips clone when .git already exists in vault root."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with caplog.at_level(logging.INFO, logger="knowledge.service"):
            await service.clone_vault()
        assert any("already initialised" in r.message for r in caplog.records)
        assert (tmp_path / self._SENTINEL).exists()

    @pytest.mark.asyncio
    async def test_clones_repo_with_dulwich(self, monkeypatch, tmp_path):
        """clone_vault calls dulwich porcelain.clone with depth=1 and token auth."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.porcelain") as mock_porcelain:
            await service.clone_vault()
        mock_porcelain.clone.assert_called_once_with(
            "https://github.com/test/repo.git",
            target=str(tmp_path),
            depth=1,
            username="x-access-token",
            password="ghp_test",
        )
        assert (tmp_path / self._SENTINEL).exists()

    @pytest.mark.asyncio
    async def test_clones_without_token(self, monkeypatch, tmp_path):
        """clone_vault omits credentials when GITHUB_TOKEN is unset."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.porcelain") as mock_porcelain:
            await service.clone_vault()
        call_kwargs = mock_porcelain.clone.call_args.kwargs
        assert "username" not in call_kwargs
        assert "password" not in call_kwargs

    @pytest.mark.asyncio
    async def test_clone_failure_logs_warning_and_writes_sentinel(
        self, monkeypatch, tmp_path, caplog
    ):
        """clone_vault logs a warning but still writes sentinel on failure."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_porcelain.clone.side_effect = Exception("network error")
            with caplog.at_level(logging.WARNING, logger="knowledge.service"):
                await service.clone_vault()
        assert any("clone failed" in r.message.lower() for r in caplog.records)
        assert (tmp_path / self._SENTINEL).exists()
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — tests reference `porcelain` which doesn't exist in service.py yet, and sentinel assertions fail.

**Step 3: Rewrite clone_vault() implementation**

Replace lines 1-59 of `knowledge/service.py`. Remove `import subprocess` and the old `clone_vault`. The new top of file:

```python
"""Startup hook that registers the knowledge scheduled jobs."""

import logging
import os
from datetime import datetime
from pathlib import Path

from dulwich import porcelain
from sqlmodel import Session

from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
_GIT_READY_SENTINEL = ".git-ready"
# 5-minute reconcile cycle. The companion _TTL_SECS=600 ensures at
# most one missed run before alerting fires (the scheduler considers
# a job stale after ttl_secs).
_INTERVAL_SECS = 300
_TTL_SECS = 600
_BACKUP_INTERVAL_SECS = 86400  # 24 hours
_BACKUP_TTL_SECS = 3600  # 1 hour timeout


async def clone_vault() -> None:
    """Clone the vault repo to pre-seed the emptyDir volume.

    Skips if VAULT_GIT_REMOTE is not set or if the vault already has a .git dir.
    Always writes a .git-ready sentinel so the obsidian sidecar can start.
    """
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    try:
        remote = os.environ.get("VAULT_GIT_REMOTE", "")
        if not remote:
            logger.info("VAULT_GIT_REMOTE not set, skipping clone")
            return

        if (vault_root / ".git").exists():
            logger.info("Vault at %s already initialised, skipping clone", vault_root)
            return

        token = os.environ.get("GITHUB_TOKEN", "")
        clone_kwargs: dict = {
            "target": str(vault_root),
            "depth": 1,
        }
        if token:
            clone_kwargs["username"] = "x-access-token"
            clone_kwargs["password"] = token

        try:
            porcelain.clone(remote, **clone_kwargs)
            logger.info("Vault cloned from git to %s", vault_root)
        except Exception as exc:
            logger.warning(
                "Vault clone failed, proceeding without pre-seed: %s", exc
            )
    finally:
        (vault_root / _GIT_READY_SENTINEL).touch()
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): rewrite clone_vault to use dulwich with git-ready sentinel"
```

---

### Task 3: Rewrite `vault_backup_handler()` to use dulwich

**Files:**

- Modify: `projects/monolith/knowledge/service.py:62-97` (replace `_git_in_vault` and `vault_backup_handler`)
- Modify: `projects/monolith/knowledge/service_test.py:315-377` (replace `TestVaultBackupHandler`)

**Step 1: Write the failing tests**

Replace the entire `TestVaultBackupHandler` class in `service_test.py` (lines 315-377) with:

```python
class TestVaultBackupHandler:
    @pytest.mark.asyncio
    async def test_skips_when_no_git_dir(self, monkeypatch, tmp_path):
        """vault_backup_handler skips when vault has no .git directory."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        result = await service.vault_backup_handler(MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_no_changes(self, monkeypatch, tmp_path):
        """vault_backup_handler does nothing when dulwich status reports no changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_status = MagicMock()
            mock_status.staged = {"add": [], "delete": [], "modify": []}
            mock_status.unstaged = []
            mock_status.untracked = []
            mock_porcelain.status.return_value = mock_status
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        mock_porcelain.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_commits_and_pushes_when_changes_exist(self, monkeypatch, tmp_path):
        """vault_backup_handler stages, commits, and pushes when there are changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_status = MagicMock()
            mock_status.staged = {"add": [], "delete": [], "modify": []}
            mock_status.unstaged = [b"file.md"]
            mock_status.untracked = []
            mock_porcelain.status.return_value = mock_status
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        mock_porcelain.add.assert_called_once_with(str(tmp_path))
        mock_porcelain.commit.assert_called_once()
        mock_porcelain.push.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_untracked_as_changes(self, monkeypatch, tmp_path):
        """vault_backup_handler treats untracked files as changes to commit."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_status = MagicMock()
            mock_status.staged = {"add": [], "delete": [], "modify": []}
            mock_status.unstaged = []
            mock_status.untracked = ["new_note.md"]
            mock_porcelain.status.return_value = mock_status
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        mock_porcelain.add.assert_called_once()
        mock_porcelain.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_failure_logs_warning(self, monkeypatch, tmp_path, caplog):
        """vault_backup_handler logs a warning when push fails."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_status = MagicMock()
            mock_status.staged = {"add": [], "delete": [], "modify": []}
            mock_status.unstaged = [b"file.md"]
            mock_status.untracked = []
            mock_porcelain.status.return_value = mock_status
            mock_porcelain.push.side_effect = Exception("rejected")
            with caplog.at_level(logging.WARNING, logger="knowledge.service"):
                await service.vault_backup_handler(MagicMock())
        assert any("push failed" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_push_uses_token_auth(self, monkeypatch, tmp_path):
        """vault_backup_handler passes token credentials to push."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_backup")
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.porcelain") as mock_porcelain:
            mock_status = MagicMock()
            mock_status.staged = {"add": [], "delete": [], "modify": []}
            mock_status.unstaged = [b"file.md"]
            mock_status.untracked = []
            mock_porcelain.status.return_value = mock_status
            await service.vault_backup_handler(MagicMock())
        push_kwargs = mock_porcelain.push.call_args.kwargs
        assert push_kwargs["username"] == "x-access-token"
        assert push_kwargs["password"] == "ghp_backup"
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — old tests reference `subprocess.run`, new tests expect dulwich porcelain.

**Step 3: Rewrite vault_backup_handler()**

Replace `_git_in_vault` and `vault_backup_handler` in `service.py` (lines 62-97) with:

```python
def _has_changes(vault_root: Path) -> bool:
    """Check if the vault has any uncommitted or untracked changes."""
    status = porcelain.status(str(vault_root))
    has_staged = any(status.staged.get(k) for k in ("add", "delete", "modify"))
    return has_staged or bool(status.unstaged) or bool(status.untracked)


async def vault_backup_handler(session: Session) -> datetime | None:
    """Scheduler handler: commit and push vault changes to GitHub."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    if not (vault_root / ".git").exists():
        logger.info("knowledge.vault-backup: no .git dir, skipping")
        return None

    if not _has_changes(vault_root):
        logger.info("knowledge.vault-backup: no changes to commit")
        return None

    token = os.environ.get("GITHUB_TOKEN", "")
    push_kwargs: dict = {}
    if token:
        push_kwargs["username"] = "x-access-token"
        push_kwargs["password"] = token

    try:
        porcelain.add(str(vault_root))
        porcelain.commit(str(vault_root), message=b"sync: vault backup")
        porcelain.push(str(vault_root), **push_kwargs)
        logger.info("knowledge.vault-backup: committed and pushed")
    except Exception as exc:
        logger.warning("knowledge.vault-backup: push failed: %s", exc)
    return None
```

**Step 4: Remove stale imports**

Ensure `import subprocess` is removed from `service.py` (no longer used). Also remove `import subprocess` from the top of `service_test.py` (line 4).

**Step 5: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: PASS

**Step 6: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): rewrite vault_backup_handler to use dulwich"
```

---

### Task 4: Gate obsidian sidecar on `.git-ready` sentinel

**Files:**

- Modify: `projects/monolith/obsidian-image/entrypoint.sh`

**Step 1: Add sentinel wait loop to entrypoint.sh**

Replace the content of `entrypoint.sh` with:

```bash
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
```

**Step 2: Verify the obsidian readiness probe test still passes**

Run: `bb remote test //projects/monolith/chart:obsidian_readiness_probe_test --config=ci`
Expected: PASS — the test checks for `/tmp/ready` sentinel which is unchanged.

**Step 3: Commit**

```bash
git add projects/monolith/obsidian-image/entrypoint.sh
git commit -m "feat(monolith): gate obsidian sidecar on .git-ready sentinel"
```

---

### Task 5: Run full test suite, bump chart version, push and create PR

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS

**Step 2: Bump chart version**

Increment the patch version in `projects/monolith/chart/Chart.yaml` and update `targetRevision` in `projects/monolith/deploy/application.yaml` to match.

**Step 3: Run format**

Run: `format`

**Step 4: Commit**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to <new-version>"
```

**Step 5: Push and create PR**

```bash
git push -u origin feat/dulwich-vault-sync
gh pr create --title "feat(knowledge): replace subprocess git with dulwich" --body "$(cat <<'EOF'
## Summary
- Replace subprocess git calls with dulwich (pure Python git) — no system `git` binary needed
- Gate obsidian sidecar on `.git-ready` sentinel file so git clone finishes before `ob sync` starts
- Clone failures are non-fatal — obsidian falls back to slow sync

## Test plan
- [ ] `bb remote test //projects/monolith/... --config=ci` passes
- [ ] Helm template renders correctly with knowledge.enabled=true
- [ ] Deploy to cluster, verify vault clones on startup in pod logs
- [ ] Verify obsidian sidecar waits for sentinel then syncs
- [ ] Verify daily backup job commits and pushes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
