"""Tests for the Claude-backed gap classifier subprocess wrapper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from knowledge.gap_classifier import (
    CLASSIFIER_VERSION,
    ClassifyStats,
    classify_stubs,
)


class _FakeProcess:
    """Minimal asyncio.subprocess.Process stand-in for tests."""

    def __init__(
        self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
    ):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:  # pragma: no cover — only called on timeout
        pass

    async def wait(self) -> None:  # pragma: no cover
        return


@pytest.mark.asyncio
async def test_classify_stubs_invokes_claude_with_correct_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Captured args prove: Read+Edit only, no Write/Bash, prompt lists stubs."""
    captured_args: list[str] = []
    captured_kwargs: dict = {}

    async def fake_spawn(*args, **kwargs):
        captured_args.extend(args)
        captured_kwargs.update(kwargs)
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    stubs = [tmp_path / "a.md", tmp_path / "b.md", tmp_path / "c.md"]
    stats = await classify_stubs(stubs, claude_bin="claude")

    assert stats == ClassifyStats(stubs_processed=3, duration_ms=stats.duration_ms)

    # claude binary + --print + --dangerously-skip-permissions + --allowedTools +
    # "Read,Edit" + -p + prompt
    assert captured_args[0] == "claude"
    assert "--allowedTools" in captured_args
    allowed_tools_idx = captured_args.index("--allowedTools")
    assert captured_args[allowed_tools_idx + 1] == "Read,Edit"

    # Prompt (the arg after -p) contains each stub path on its own bulleted line
    p_idx = captured_args.index("-p")
    prompt = captured_args[p_idx + 1]
    for stub in stubs:
        assert f"- {stub}" in prompt

    # Classifier version is interpolated into the prompt
    assert CLASSIFIER_VERSION in prompt

    # The 4-class rubric must be present — insurance against accidental
    # prompt rot that would silently invalidate classifications.
    for cls in ("external", "internal", "hybrid", "parked"):
        assert cls in prompt, f"prompt missing class: {cls}"

    # HOME override protecting claude's ~/.claude write
    assert captured_kwargs["env"]["HOME"] == "/tmp"


@pytest.mark.asyncio
async def test_classify_stubs_handles_subprocess_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subprocess timeout returns ClassifyStats without raising."""

    kill_called: list[bool] = []

    async def fake_spawn(*args, **kwargs):
        process = _FakeProcess()

        async def slow_communicate():
            await asyncio.sleep(10)  # longer than our patched timeout
            return (b"", b"")

        def kill():
            kill_called.append(True)

        process.communicate = slow_communicate  # type: ignore[method-assign]
        process.kill = kill  # type: ignore[method-assign]
        return process

    # Patch the module's timeout constant to something we can actually wait out.
    monkeypatch.setattr("knowledge.gap_classifier._CLASSIFY_TIMEOUT_SECS", 0.05)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    stats = await classify_stubs([tmp_path / "a.md"], claude_bin="claude")
    assert stats.stubs_processed == 1
    assert stats.duration_ms >= 0
    assert kill_called == [True]


@pytest.mark.asyncio
async def test_classify_stubs_logs_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-zero subprocess exit logs a warning with stderr excerpt."""

    async def fake_spawn(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"auth: invalid token")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    with caplog.at_level(logging.WARNING, logger="knowledge.gap_classifier"):
        stats = await classify_stubs([tmp_path / "a.md"], claude_bin="claude")

    assert stats.stubs_processed == 1
    assert "exit=1" in caplog.text
    assert "invalid token" in caplog.text


@pytest.mark.asyncio
async def test_classify_stubs_empty_batch_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty stub list returns zero stats without spawning anything."""
    spawned: list[bool] = []

    async def fake_spawn(*args, **kwargs):
        spawned.append(True)
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    stats = await classify_stubs([], claude_bin="claude")
    assert stats == ClassifyStats(stubs_processed=0, duration_ms=0)
    assert spawned == []


@pytest.mark.asyncio
async def test_classify_stubs_rejects_relative_paths(tmp_path: Path) -> None:
    """Relative stub paths raise a ValueError before any subprocess work."""
    with pytest.raises(ValueError, match="requires absolute paths"):
        await classify_stubs([Path("relative.md")], claude_bin="claude")
