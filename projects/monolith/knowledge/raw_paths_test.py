"""Tests for raw path + content hash helpers."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from knowledge.raw_paths import (
    compute_raw_id,
    raw_target_path,
    RAW_ROOT_NAME,
    GRANDFATHERED_SUBDIR,
)


def test_compute_raw_id_is_sha256_of_bytes():
    content = "# Hello\n\nBody."
    expected = "39c483b62cff864432b5302bd48b97d716d5713a9f53581167a17507086a301e"
    assert compute_raw_id(content) == expected


def test_compute_raw_id_is_stable_across_calls():
    content = "foo"
    assert compute_raw_id(content) == compute_raw_id(content)


def test_raw_target_path_uses_date_and_hash_prefix():
    created_at = datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)
    raw_id = "abcdef1234567890" + "0" * 48  # valid-length sha256
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="My Cool Note!",
        created_at=created_at,
    )
    assert p == Path("/vault/_raw/2026/04/09/abcdef12-my-cool-note.md")


def test_raw_target_path_grandfathered_uses_flat_subdir():
    raw_id = "abcdef1234567890" + "0" * 48
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="Old Note",
        grandfathered=True,
    )
    assert p == Path("/vault/_raw/grandfathered/abcdef12-old-note.md")


def test_raw_target_path_handles_title_with_only_punctuation():
    raw_id = "fedcba9876543210" + "0" * 48
    p = raw_target_path(
        vault_root=Path("/vault"),
        raw_id=raw_id,
        title="???",
        created_at=datetime(2026, 4, 9, tzinfo=timezone.utc),
    )
    # Slug falls back to "note"
    assert p.name == "fedcba98-note.md"


def test_raw_target_path_raises_without_created_at():
    with pytest.raises(ValueError, match="created_at is required"):
        raw_target_path(
            vault_root=Path("/vault"),
            raw_id="a" * 64,
            title="test",
        )


def test_raw_root_name_constant():
    assert RAW_ROOT_NAME == "_raw"
    assert GRANDFATHERED_SUBDIR == "grandfathered"
