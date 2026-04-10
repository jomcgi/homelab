"""Tests for _wait_for_vault_sync() in app.main.

Covers:
- Returns immediately when vault_root does not exist
- Returns after logging 'ready' when .md files are present on first check
- Polls until .md files appear after a few iterations, then returns
- Times out after 60 iterations, logs a warning, and returns
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, call

import pytest

# Ensure no valid static directory is set (mirrors other main_* test files)
os.environ.pop("STATIC_DIR", None)

from app.main import _wait_for_vault_sync  # noqa: E402


# ---------------------------------------------------------------------------
# (1) Returns immediately when vault_root does not exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_vault_sync_returns_immediately_when_root_missing():
    """_wait_for_vault_sync returns at once when VAULT_ROOT path does not exist."""
    with patch.dict(os.environ, {"VAULT_ROOT": "/nonexistent/vault/path/xyz123"}):
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            await _wait_for_vault_sync()

    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_vault_sync_never_logs_ready_when_root_missing():
    """No 'Vault sync ready' log when vault_root does not exist."""
    with patch.dict(os.environ, {"VAULT_ROOT": "/nonexistent/vault/path/xyz123"}):
        with patch("app.main.logger") as mock_logger:
            await _wait_for_vault_sync()

    info_msgs = [str(c) for c in mock_logger.info.call_args_list]
    assert not any("ready" in m.lower() for m in info_msgs)
    mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# (2) Returns after logging 'ready' when .md files exist on first check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_vault_sync_returns_on_first_check_with_md_file():
    """Returns immediately after first rglob finds a .md file without sleeping."""
    with tempfile.TemporaryDirectory() as vault_dir:
        # Create a markdown file in the vault
        (Path(vault_dir) / "note.md").write_text("# Note")

        sleep_mock = AsyncMock()
        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", sleep_mock):
                await _wait_for_vault_sync()

    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_vault_sync_logs_ready_when_md_found():
    """Logs 'Vault sync ready' when .md files are found."""
    with tempfile.TemporaryDirectory() as vault_dir:
        (Path(vault_dir) / "note.md").write_text("# Note")

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("app.main.logger") as mock_logger:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await _wait_for_vault_sync()

    info_msgs = [str(c) for c in mock_logger.info.call_args_list]
    assert any("Vault sync ready" in m for m in info_msgs)


@pytest.mark.asyncio
async def test_wait_for_vault_sync_logs_waiting_message_before_polling():
    """Logs an informational 'Waiting' message at startup."""
    with tempfile.TemporaryDirectory() as vault_dir:
        (Path(vault_dir) / "note.md").write_text("# Note")

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("app.main.logger") as mock_logger:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await _wait_for_vault_sync()

    info_msgs = [str(c) for c in mock_logger.info.call_args_list]
    assert any("Waiting for Obsidian vault sync" in m for m in info_msgs)


@pytest.mark.asyncio
async def test_wait_for_vault_sync_finds_nested_md_file():
    """Finds .md files in subdirectories (rglob, not just top-level)."""
    with tempfile.TemporaryDirectory() as vault_dir:
        subdir = Path(vault_dir) / "subfolder" / "nested"
        subdir.mkdir(parents=True)
        (subdir / "deep.md").write_text("# Deep note")

        sleep_mock = AsyncMock()
        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", sleep_mock):
                await _wait_for_vault_sync()

    sleep_mock.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_vault_sync_ignores_non_md_files():
    """Does not treat non-.md files (e.g. .txt, .json) as vault-ready signal."""
    with tempfile.TemporaryDirectory() as vault_dir:
        (Path(vault_dir) / "config.json").write_text("{}")
        (Path(vault_dir) / "readme.txt").write_text("readme")

        sleep_mock = AsyncMock()
        # We limit iterations to avoid an infinite loop in this test —
        # we patch rglob to return empty after the non-md files are "present"
        call_count = [0]
        orig_rglob = Path.rglob

        def limited_rglob(self, pattern):
            if call_count[0] < 3:
                call_count[0] += 1
                return iter([])  # never finds any .md files
            raise StopIteration  # force the loop to exhaust naturally

        # Instead: patch the vault_root.rglob to return empty for all 60 tries
        # by just making .md file appear on call 3
        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            # Create an .md file after 2 sleeps
            async def side_effect_sleep(seconds):  # noqa: ARG001
                if sleep_mock.call_count == 2:
                    (Path(vault_dir) / "note.md").write_text("# Note")

            sleep_mock.side_effect = side_effect_sleep
            with patch("asyncio.sleep", sleep_mock):
                await _wait_for_vault_sync()

    # Slept exactly 2 times (found on 3rd iteration)
    assert sleep_mock.call_count == 2


# ---------------------------------------------------------------------------
# (3) Polls until .md files appear after a few iterations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_vault_sync_polls_until_md_file_appears():
    """Sleeps between iterations until .md file is created in vault."""
    with tempfile.TemporaryDirectory() as vault_dir:
        sleep_count = [0]

        async def side_effect_sleep(seconds):  # noqa: ARG001
            sleep_count[0] += 1
            if sleep_count[0] == 3:
                # Create the markdown file after 3 sleeps
                (Path(vault_dir) / "note.md").write_text("# Note")

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", side_effect=side_effect_sleep):
                await _wait_for_vault_sync()

    assert sleep_count[0] == 3


@pytest.mark.asyncio
async def test_wait_for_vault_sync_sleeps_5_seconds_per_iteration():
    """Each iteration sleeps exactly 5 seconds."""
    with tempfile.TemporaryDirectory() as vault_dir:
        sleep_args = []

        async def capturing_sleep(seconds):
            sleep_args.append(seconds)
            if len(sleep_args) == 2:
                (Path(vault_dir) / "note.md").write_text("# Note")

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", side_effect=capturing_sleep):
                await _wait_for_vault_sync()

    assert all(s == 5 for s in sleep_args)


# ---------------------------------------------------------------------------
# (4) Timeout after 60 iterations — logs warning and returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_vault_sync_times_out_after_60_iterations():
    """After 60 iterations without finding .md files, returns without blocking."""
    with tempfile.TemporaryDirectory() as vault_dir:
        sleep_mock = AsyncMock()

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", sleep_mock):
                await _wait_for_vault_sync()

    # 60 iterations × sleep(5) each
    assert sleep_mock.call_count == 60


@pytest.mark.asyncio
async def test_wait_for_vault_sync_logs_warning_on_timeout():
    """Logs a warning message when the 5-minute timeout is reached."""
    with tempfile.TemporaryDirectory() as vault_dir:
        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch("app.main.logger") as mock_logger:
                    await _wait_for_vault_sync()

    assert mock_logger.warning.called
    warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
    assert any("timed out" in m.lower() for m in warning_msgs)


@pytest.mark.asyncio
async def test_wait_for_vault_sync_sleeps_exactly_5s_in_timeout_path():
    """Each of the 60 timeout-path iterations sleeps exactly 5 seconds."""
    with tempfile.TemporaryDirectory() as vault_dir:
        sleep_mock = AsyncMock()

        with patch.dict(os.environ, {"VAULT_ROOT": vault_dir}):
            with patch("asyncio.sleep", sleep_mock):
                await _wait_for_vault_sync()

    for c in sleep_mock.call_args_list:
        assert c == call(5)


# ---------------------------------------------------------------------------
# Default VAULT_ROOT value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_vault_sync_uses_default_vault_root_when_env_unset():
    """Uses '/vault' as default VAULT_ROOT when env var is not set."""
    env_without_vault = {k: v for k, v in os.environ.items() if k != "VAULT_ROOT"}

    with patch.dict(os.environ, env_without_vault, clear=True):
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            # /vault does not exist in test environment — returns immediately
            await _wait_for_vault_sync()

    sleep_mock.assert_not_called()
