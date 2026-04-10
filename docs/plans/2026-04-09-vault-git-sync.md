# Vault Git Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the slow `_wait_for_vault_sync()` polling loop with a fast `git clone`, and add a daily scheduled job that commits+pushes vault changes to GitHub as a backup.

**Architecture:** The monolith Python app clones the vault repo on startup (pre-seeding the `emptyDir` volume), then the obsidian headless-sync sidecar handles live sync as before. A new scheduler job (`knowledge.vault-backup`) runs once per day, committing and pushing any changes to GitHub. Only one pod acquires the scheduler lock via `SKIP LOCKED`.

**Tech Stack:** Python, subprocess (git), existing scheduler framework, Helm

---

### Task 1: Add `clone_vault()` and `vault_backup_handler()` to knowledge/service.py

**Files:**

- Modify: `projects/monolith/knowledge/service.py`
- Test: `projects/monolith/knowledge/service_test.py`

**Step 1: Write tests for `clone_vault()`**

Add a new `TestCloneVault` class to `service_test.py` with these tests:

```python
class TestCloneVault:
    @pytest.mark.asyncio
    async def test_skips_when_git_remote_unset(self, monkeypatch, caplog):
        """clone_vault returns immediately when VAULT_GIT_REMOTE is empty."""
        monkeypatch.delenv("VAULT_GIT_REMOTE", raising=False)
        with caplog.at_level(logging.INFO, logger="knowledge.service"):
            await service.clone_vault()
        assert any("VAULT_GIT_REMOTE not set" in r.message for r in caplog.records)

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

    @pytest.mark.asyncio
    async def test_clones_repo(self, monkeypatch, tmp_path):
        """clone_vault runs git clone with depth=1 and token-embedded URL."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await service.clone_vault()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert "clone" in cmd
        assert "--depth=1" in cmd
        assert "x-access-token:ghp_test@github.com" in cmd[3]
        assert str(tmp_path) in cmd

    @pytest.mark.asyncio
    async def test_clone_failure_logs_warning_and_continues(self, monkeypatch, tmp_path, caplog):
        """clone_vault logs a warning but does not raise on clone failure."""
        monkeypatch.setenv("VAULT_GIT_REMOTE", "https://github.com/test/repo.git")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        with patch("knowledge.service.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with caplog.at_level(logging.WARNING, logger="knowledge.service"):
                await service.clone_vault()
        assert any("clone failed" in r.message.lower() for r in caplog.records)
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — `clone_vault` does not exist yet.

**Step 3: Write `clone_vault()` implementation**

Add to `knowledge/service.py`:

```python
import subprocess

async def clone_vault() -> None:
    """Clone the vault repo to pre-seed the emptyDir volume.

    Skips if VAULT_GIT_REMOTE is not set or if the vault already has a .git dir.
    Embeds GITHUB_TOKEN in the clone URL for auth.
    """
    remote = os.environ.get("VAULT_GIT_REMOTE", "")
    if not remote:
        logger.info("VAULT_GIT_REMOTE not set, skipping clone")
        return

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    if (vault_root / ".git").exists():
        logger.info("Vault at %s already initialised, skipping clone", vault_root)
        return

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        remote = remote.replace("https://", f"https://x-access-token:{token}@")

    try:
        subprocess.run(
            ["git", "clone", "--depth=1", remote, str(vault_root)],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Vault cloned from git to %s", vault_root)
    except subprocess.CalledProcessError as exc:
        logger.warning("Vault clone failed, proceeding without pre-seed: %s", exc.stderr)
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: PASS

**Step 5: Write tests for `vault_backup_handler()`**

Add a `TestVaultBackupHandler` class:

```python
class TestVaultBackupHandler:
    @pytest.mark.asyncio
    async def test_skips_when_no_changes(self, monkeypatch, tmp_path):
        """vault_backup_handler does nothing when git status is clean."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        with patch("knowledge.service.subprocess.run") as mock_run:
            # git status --porcelain returns empty
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        # Only git status was called, no commit/push
        assert mock_run.call_count == 1

    @pytest.mark.asyncio
    async def test_commits_and_pushes_when_changes_exist(self, monkeypatch, tmp_path):
        """vault_backup_handler commits and pushes when there are uncommitted changes."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "status" in cmd:
                return MagicMock(stdout=" M file.md\n", returncode=0)
            return MagicMock(returncode=0)
        with patch("knowledge.service.subprocess.run", side_effect=fake_run):
            result = await service.vault_backup_handler(MagicMock())
        assert result is None
        cmds = [" ".join(c) for c in calls]
        assert any("git add -A" in c for c in cmds)
        assert any("git commit" in c for c in cmds)
        assert any("git push" in c for c in cmds)

    @pytest.mark.asyncio
    async def test_skips_when_no_git_dir(self, monkeypatch, tmp_path):
        """vault_backup_handler skips when vault has no .git directory."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        # No .git dir
        result = await service.vault_backup_handler(MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_push_failure_logs_warning(self, monkeypatch, tmp_path, caplog):
        """vault_backup_handler logs a warning when push fails."""
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        (tmp_path / ".git").mkdir()
        call_count = [0]
        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            if "status" in cmd:
                return MagicMock(stdout=" M file.md\n", returncode=0)
            if "push" in cmd:
                raise subprocess.CalledProcessError(1, "git push", stderr="rejected")
            return MagicMock(returncode=0)
        with patch("knowledge.service.subprocess.run", side_effect=fake_run):
            with caplog.at_level(logging.WARNING, logger="knowledge.service"):
                await service.vault_backup_handler(MagicMock())
        assert any("push failed" in r.message.lower() for r in caplog.records)
```

**Step 6: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — `vault_backup_handler` does not exist yet.

**Step 7: Write `vault_backup_handler()` implementation**

Add to `knowledge/service.py`:

```python
_BACKUP_INTERVAL_SECS = 86400  # 24 hours
_BACKUP_TTL_SECS = 3600  # 1 hour timeout


def _git_in_vault(*args: str) -> subprocess.CompletedProcess:
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    return subprocess.run(
        ["git", *args],
        cwd=vault_root,
        capture_output=True,
        text=True,
        check=True,
    )


async def vault_backup_handler(session: Session) -> datetime | None:
    """Scheduler handler: commit and push vault changes to GitHub."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    if not (vault_root / ".git").exists():
        logger.info("knowledge.vault-backup: no .git dir, skipping")
        return None

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=vault_root,
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        logger.info("knowledge.vault-backup: no changes to commit")
        return None

    try:
        _git_in_vault("add", "-A")
        _git_in_vault("commit", "-m", "sync: vault backup")
        _git_in_vault("push")
        logger.info("knowledge.vault-backup: committed and pushed")
    except subprocess.CalledProcessError as exc:
        logger.warning("knowledge.vault-backup: push failed: %s", exc.stderr)
    return None
```

**Step 8: Register the backup job in `on_startup()`**

Add to the end of `on_startup()`:

```python
    register_job(
        session,
        name="knowledge.vault-backup",
        interval_secs=_BACKUP_INTERVAL_SECS,
        handler=vault_backup_handler,
        ttl_secs=_BACKUP_TTL_SECS,
    )
```

**Step 9: Update `TestOnStartup` tests**

Update `test_registers_garden_and_reconcile_jobs` to also assert `"knowledge.vault-backup" in names`.

**Step 10: Run all tests**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: PASS

**Step 11: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): add vault git clone and daily backup job"
```

---

### Task 2: Replace `_wait_for_vault_sync()` with `clone_vault()` in app/main.py

**Files:**

- Modify: `projects/monolith/app/main.py`
- Modify: `projects/monolith/app/main_vault_sync_test.py`

**Step 1: Update `main.py`**

Replace the `_wait_for_vault_sync()` function body and its call site in the lifespan:

```python
# Remove the _wait_for_vault_sync() function entirely.
# In lifespan(), replace:
#     await _wait_for_vault_sync()
# with:
    from knowledge.service import clone_vault
    await clone_vault()
```

**Step 2: Rewrite `main_vault_sync_test.py`**

Replace all existing tests with tests for the new clone_vault call in lifespan. The clone_vault function itself is tested in service_test.py — here we just verify the lifespan calls it:

```python
"""Tests that lifespan calls clone_vault on startup."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.pop("STATIC_DIR", None)


@pytest.mark.asyncio
async def test_lifespan_calls_clone_vault():
    """Lifespan calls clone_vault() before starting the scheduler."""
    mock_clone = AsyncMock()
    with (
        patch("knowledge.service.clone_vault", mock_clone),
        patch("app.main._wait_for_sidecar", new_callable=AsyncMock),
        patch("shared.scheduler.run_scheduler_loop", new_callable=AsyncMock),
        patch("app.db.get_engine"),
        patch("home.service.on_startup"),
        patch("knowledge.service.on_startup"),
        patch("shared.service.on_startup"),
    ):
        from app.main import lifespan, app
        async with lifespan(app):
            pass
    mock_clone.assert_awaited_once()
```

**Step 3: Run tests**

Run: `bb remote test //projects/monolith:main_vault_sync_test --config=ci`
Expected: PASS

**Step 4: Commit**

```bash
git add projects/monolith/app/main.py projects/monolith/app/main_vault_sync_test.py
git commit -m "refactor(monolith): replace vault sync polling with git clone"
```

---

### Task 3: Add Helm values and env vars for vault git sync

**Files:**

- Modify: `projects/monolith/chart/values.yaml`
- Modify: `projects/monolith/chart/templates/deployment.yaml`
- Modify: `projects/monolith/deploy/values.yaml`

**Step 1: Add `gitRemote` to chart defaults**

In `projects/monolith/chart/values.yaml`, add under `knowledge`:

```yaml
knowledge:
  enabled: false
  gitRemote: ""
  headlessSync:
    # ... existing
```

**Step 2: Add env vars to deployment template**

In `projects/monolith/chart/templates/deployment.yaml`, add inside the backend container's `env:` block, within the `{{- if .Values.knowledge.enabled }}` guard (after the existing `VAULT_ROOT` area or alongside other knowledge env vars). Since `VAULT_ROOT` is currently set implicitly via the mount path, we need to add both `VAULT_GIT_REMOTE` and `VAULT_ROOT`:

```yaml
            {{- if .Values.knowledge.enabled }}
            - name: VAULT_ROOT
              value: {{ .Values.knowledge.vault.mountPath }}
            {{- if .Values.knowledge.gitRemote }}
            - name: VAULT_GIT_REMOTE
              value: {{ .Values.knowledge.gitRemote | quote }}
            {{- end }}
            {{- end }}
```

Note: `GITHUB_TOKEN` is already set on the backend container from the `chat.changelog` section.

**Step 3: Set deploy values**

In `projects/monolith/deploy/values.yaml`, add under `knowledge`:

```yaml
knowledge:
  enabled: true
  gitRemote: "https://github.com/jomcgi/obsidian-vault.git"
  headlessSync:
    vaultName: "jomcgi"
```

**Step 4: Verify Helm renders correctly**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A2 VAULT_GIT_REMOTE`
Expected: Shows the env var with the correct value.

**Step 5: Commit**

```bash
git add projects/monolith/chart/values.yaml projects/monolith/chart/templates/deployment.yaml projects/monolith/deploy/values.yaml
git commit -m "feat(monolith): add vault git sync helm configuration"
```

---

### Task 4: Run full test suite and bump chart version

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS

**Step 2: Bump chart version**

Bump the patch version in `projects/monolith/chart/Chart.yaml` and update `targetRevision` in `projects/monolith/deploy/application.yaml` to match.

**Step 3: Run format**

Run: `format`

**Step 4: Commit**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to <new-version>"
```

**Step 5: Push and create PR**

```bash
git push -u origin feat/vault-git-sync
gh pr create --title "feat(knowledge): add vault git clone and daily backup" --body "..."
```
