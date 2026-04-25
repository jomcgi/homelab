"""Tests for chat.vault_export."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from chat.vault_export import write_channel_summary, write_user_summary


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a vault root with the sync-ready sentinel in place."""
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    (tmp_path / ".sync-ready").touch()
    return tmp_path


def _split_frontmatter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n")
    fm_end = text.index("\n---\n", 4)
    fm = yaml.safe_load(text[4:fm_end])
    body = text[fm_end + 5 :].strip()
    return fm, body


def test_write_user_summary_creates_file(vault: Path) -> None:
    write_user_summary(
        channel_id="123",
        user_id="456",
        username="alice",
        summary="Loves cats and Rust.",
        last_message_id=789,
        updated_at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc),
    )

    path = vault / "_discord" / "123" / "users" / "456.md"
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    assert fm == {
        "type": "discord-user-summary",
        "channel_id": "123",
        "user_id": "456",
        "username": "alice",
        "last_message_id": 789,
        "updated_at": "2026-04-25T12:00:00+00:00",
    }
    assert body == "Loves cats and Rust."


def test_write_channel_summary_creates_file(vault: Path) -> None:
    write_channel_summary(
        channel_id="123",
        summary="A general chat channel about software.",
        message_count=1234,
        last_message_id=789,
        updated_at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc),
    )

    path = vault / "_discord" / "123" / "channel.md"
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    assert fm == {
        "type": "discord-channel-summary",
        "channel_id": "123",
        "message_count": 1234,
        "last_message_id": 789,
        "updated_at": "2026-04-25T12:00:00+00:00",
    }
    assert body == "A general chat channel about software."


def test_skip_when_vault_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    # Note: no .sync-ready sentinel.

    write_user_summary(
        channel_id="123",
        user_id="456",
        username="alice",
        summary="Hi",
        last_message_id=1,
        updated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    write_channel_summary(
        channel_id="123",
        summary="Hi",
        message_count=1,
        last_message_id=1,
        updated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )

    assert not (tmp_path / "_discord").exists()


def test_replaces_existing_file(vault: Path) -> None:
    write_user_summary(
        channel_id="123",
        user_id="456",
        username="alice",
        summary="First version.",
        last_message_id=1,
        updated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    write_user_summary(
        channel_id="123",
        user_id="456",
        username="alice",
        summary="Second version.",
        last_message_id=2,
        updated_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    text = (vault / "_discord" / "123" / "users" / "456.md").read_text(encoding="utf-8")
    assert "Second version." in text
    assert "First version." not in text


def test_username_with_special_chars_round_trips(vault: Path) -> None:
    """Tricky usernames must survive a YAML write/read cycle."""
    tricky = 'alice "the great": #1 \U0001f600'
    write_user_summary(
        channel_id="123",
        user_id="456",
        username=tricky,
        summary="Hi",
        last_message_id=1,
        updated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )

    text = (vault / "_discord" / "123" / "users" / "456.md").read_text(encoding="utf-8")
    fm, _ = _split_frontmatter(text)
    assert fm["username"] == tricky
