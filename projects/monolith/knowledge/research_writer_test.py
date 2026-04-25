"""Tests for research raw + quarantine writers."""

from __future__ import annotations

import yaml

from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_validator import ValidatedClaim, ValidatedResearch
from knowledge.research_writer import (
    FAILED_RESEARCH_DIR,
    INBOX_RESEARCH_DIR,
    quarantine,
    write_research_raw,
)


def test_write_research_raw_creates_inbox_research_file_with_full_frontmatter(tmp_path):
    note = ResearchNote(
        summary="A merkle tree is a hash-chained tree.",
        claims=[
            Claim(text="A merkle tree hashes pairs of children."),
            Claim(text="Used in Bitcoin."),
        ],
    )
    sources = [
        SourceEntry(
            tool="web_fetch",
            url="https://a.com",
            content_hash="sha256:abc",
            fetched_at="2026-04-25T09:00:00Z",
        ),
        SourceEntry(tool="search_knowledge", query="merkle", note_ids=["my-note"]),
        SourceEntry(
            tool="web_search", query="merkle tree", result_urls=["https://b.com"]
        ),
    ]
    supported = [
        ValidatedClaim(
            text="A merkle tree hashes pairs of children.",
            verdict="supported",
            reason="from a.com",
        ),
        ValidatedClaim(
            text="Used in Bitcoin.", verdict="supported", reason="common knowledge"
        ),
    ]

    path = write_research_raw(
        vault_root=tmp_path,
        slug="merkle-tree",
        title="merkle-tree",
        summary=note.summary,
        supported_claims=supported,
        sources=sources,
        claims_dropped=0,
        qwen_model="qwen3.6-27b",
        sonnet_model="sonnet-4-6",
        researched_at="2026-04-25T10:00:00Z",
    )

    assert path == tmp_path / INBOX_RESEARCH_DIR / "merkle-tree.md"
    text = path.read_text()
    assert text.startswith("---\n")
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["type"] == "research"
    assert fm["id"] == "merkle-tree"
    assert fm["derived_from_gap"] == "merkle-tree"
    assert fm["claims_supported"] == 2
    assert fm["claims_dropped"] == 0
    assert len(fm["sources"]) == 3
    assert fm["sources"][0]["tool"] == "web_fetch"
    assert fm["sources"][0]["url"] == "https://a.com"
    assert "merkle tree hashes pairs" in text
    assert "Used in Bitcoin" in text


def test_write_research_raw_drops_unsupported_claims_from_body(tmp_path):
    """Only supported claims appear in the body — dropped claims live in claims_dropped count."""
    sources = [
        SourceEntry(
            tool="web_fetch", url="https://a.com", content_hash="x", fetched_at="t"
        )
    ]
    supported = [ValidatedClaim(text="kept", verdict="supported", reason="ok")]

    path = write_research_raw(
        vault_root=tmp_path,
        slug="x",
        title="x",
        summary="s",
        supported_claims=supported,
        sources=sources,
        claims_dropped=2,
        qwen_model="q",
        sonnet_model="s",
        researched_at="t",
    )

    text = path.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["claims_supported"] == 1
    assert fm["claims_dropped"] == 2
    assert "kept" in text


def test_quarantine_writes_failed_research_file_with_attempt_suffix(tmp_path):
    note = ResearchNote(summary="bad", claims=[Claim(text="unsubstantiated")])
    validated = ValidatedResearch(
        claims=[
            ValidatedClaim(
                text="unsubstantiated", verdict="unsupported", reason="no source"
            ),
        ]
    )

    path = quarantine(
        vault_root=tmp_path,
        slug="x",
        attempt=2,
        draft_note=note,
        validated=validated,
        sources=[],
        qwen_model="q",
        sonnet_model="s",
        researched_at="t",
    )

    assert path == tmp_path / FAILED_RESEARCH_DIR / "x-2.md"
    text = path.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["type"] == "failed_research"
    assert fm["attempt"] == 2
    assert fm["derived_from_gap"] == "x"
    assert "unsubstantiated" in text


def test_write_research_raw_byte_stable_on_idempotent_call(tmp_path):
    """Calling write_research_raw twice with identical args produces an identical file (byte-stable).

    Uses multiple sources and claims so that any list-order regression
    (e.g. ``sorted(...)`` or ``list(set(...))``) in the writer would
    surface as a byte-diff between successive calls.
    """
    sources = [
        SourceEntry(
            tool="web_fetch",
            url="https://a.com",
            content_hash="sha256:abc",
            fetched_at="2026-04-25T09:00:00Z",
        ),
        SourceEntry(tool="search_knowledge", query="merkle", note_ids=["my-note"]),
        SourceEntry(
            tool="web_search", query="merkle tree", result_urls=["https://b.com"]
        ),
    ]
    supported = [
        ValidatedClaim(
            text="A merkle tree hashes pairs of children.",
            verdict="supported",
            reason="from a.com",
        ),
        ValidatedClaim(
            text="Used in Bitcoin.", verdict="supported", reason="common knowledge"
        ),
    ]

    args = dict(
        vault_root=tmp_path,
        slug="merkle-tree",
        title="merkle-tree",
        summary="A merkle tree is a hash-chained tree.",
        supported_claims=supported,
        sources=sources,
        claims_dropped=0,
        qwen_model="qwen3.6-27b",
        sonnet_model="sonnet-4-6",
        researched_at="2026-04-25T10:00:00Z",
    )
    path = write_research_raw(**args)
    first = path.read_bytes()
    write_research_raw(**args)
    second = path.read_bytes()
    assert first == second


def test_quarantine_byte_stable_on_idempotent_call(tmp_path):
    """Calling quarantine twice with identical args produces an identical file (byte-stable).

    Exercises multi-element ``sonnet_reasons`` and ``sources_attempted``
    plus populated ``parse_error`` / ``timed_out`` so any list-order or
    serialization regression in the quarantine writer would surface.
    """
    draft_note = ResearchNote(
        summary="A merkle tree is a hash-chained tree.",
        claims=[
            Claim(text="A merkle tree hashes pairs of children."),
            Claim(text="Used in Bitcoin."),
        ],
    )
    validated = ValidatedResearch(
        claims=[
            ValidatedClaim(
                text="A merkle tree hashes pairs of children.",
                verdict="unsupported",
                reason="no source",
            ),
            ValidatedClaim(
                text="Used in Bitcoin.",
                verdict="speculative",
                reason="no direct evidence retrieved",
            ),
        ],
        timed_out=True,
        parse_error="boom",
    )
    sources = [
        SourceEntry(
            tool="web_fetch",
            url="https://a.com",
            content_hash="sha256:abc",
            fetched_at="2026-04-25T09:00:00Z",
        ),
        SourceEntry(tool="search_knowledge", query="merkle", note_ids=["my-note"]),
        SourceEntry(
            tool="web_search", query="merkle tree", result_urls=["https://b.com"]
        ),
    ]

    args = dict(
        vault_root=tmp_path,
        slug="merkle-tree",
        attempt=3,
        draft_note=draft_note,
        validated=validated,
        sources=sources,
        qwen_model="qwen3.6-27b",
        sonnet_model="sonnet-4-6",
        researched_at="2026-04-25T10:00:00Z",
    )
    path = quarantine(**args)
    first = path.read_bytes()
    quarantine(**args)
    second = path.read_bytes()
    assert first == second
