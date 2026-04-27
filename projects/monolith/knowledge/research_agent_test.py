"""Tests for the Sonnet-driven research agent (claude --print subprocess)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.research_agent import (
    AGENT_MODEL,
    Claim,  # noqa: F401  (asserted at import time per the export checklist)
    ResearchResult,
    SONNET_ALLOWED_TOOLS,
    SourceEntry,
    run_research,
)


def _stream_json(*events: dict) -> bytes:
    return ("\n".join(json.dumps(e) for e in events) + "\n").encode()


def _tool_use(tu_id: str, name: str, **inp) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "id": tu_id, "name": name, "input": inp}]
        },
    }


def _tool_result(tu_id: str, *, is_error: bool = False) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tu_id, "is_error": is_error}
            ]
        },
    }


def _final_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _make_proc(stdout: bytes, returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_subprocess_invoked_with_expected_flags(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "research",
                    "reason": "publicly-researchable concept",
                    "summary": "x",
                    "claims": [{"text": "y", "source_refs": ["https://example.com/a"]}],
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    captured: dict = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        return proc

    with patch(
        "asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec
    ):
        await run_research(term="foo", vault_root=tmp_path)

    args = captured["args"]
    assert args[0] == "claude"
    assert "--print" in args
    assert "--output-format" in args
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in args
    assert "--dangerously-skip-permissions" in args
    assert "--model" in args
    assert args[args.index("--model") + 1] == AGENT_MODEL
    assert "--allowedTools" in args
    assert args[args.index("--allowedTools") + 1] == SONNET_ALLOWED_TOOLS
    assert captured["cwd"] == tmp_path
    assert captured["env"]["HOME"] == "/tmp"


@pytest.mark.asyncio
async def test_research_disposition_with_valid_citations(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "research",
                    "reason": "publicly-researchable concept",
                    "summary": "term means X",
                    "claims": [
                        {"text": "Claim A", "source_refs": ["https://example.com/a"]},
                    ],
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert isinstance(result, ResearchResult)
    assert result.disposition == "research"
    assert result.reason == "publicly-researchable concept"
    assert result.note is not None
    assert result.note.summary == "term means X"
    assert [c.text for c in result.note.claims] == ["Claim A"]
    assert result.sources == (
        SourceEntry(tool="WebFetch", ref="https://example.com/a"),
    )


@pytest.mark.asyncio
async def test_research_disposition_drops_unsourced_claims(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "research",
                    "reason": "publicly-researchable",
                    "summary": "x",
                    "claims": [
                        {"text": "kept", "source_refs": ["https://example.com/a"]},
                        {
                            "text": "dropped (un-retrieved url)",
                            "source_refs": ["https://example.com/never-fetched"],
                        },
                        {"text": "also dropped (no refs)", "source_refs": []},
                    ],
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert result.disposition == "research"
    assert result.note is not None
    assert [c.text for c in result.note.claims] == ["kept"]


@pytest.mark.asyncio
async def test_research_disposition_all_claims_dropped_yields_empty_claims(
    tmp_path: Path,
) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebSearch", query="foo"),  # search only, no fetches
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "research",
                    "reason": "publicly-researchable",
                    "summary": "x",
                    "claims": [
                        {
                            "text": "unsupported",
                            "source_refs": ["https://hallucinated"],
                        }
                    ],
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert result.disposition == "research"
    assert result.note is not None
    assert result.note.claims == []


@pytest.mark.asyncio
async def test_personal_disposition(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "Glob", pattern="**/*.md"),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "personal",
                    "reason": "term appears only in journal-style notes; only Joe can resolve",
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert result.disposition == "personal"
    assert result.reason.startswith("term appears only")
    assert result.note is None


@pytest.mark.asyncio
async def test_discard_disposition(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "Grep", pattern="foo"),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "discard",
                    "reason": "looks like a typo of `food`",
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert result.disposition == "discard"
    assert result.reason == "looks like a typo of `food`"
    assert result.note is None


@pytest.mark.asyncio
async def test_invalid_disposition_raises(tmp_path: Path) -> None:
    transcript = _stream_json(
        _final_text(
            json.dumps(
                {
                    "disposition": "research_more",  # not in the enum
                    "reason": "x",
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RuntimeError, match="invalid disposition"):
            await run_research(term="foo", vault_root=tmp_path)


@pytest.mark.asyncio
async def test_subprocess_nonzero_exit_raises(tmp_path: Path) -> None:
    proc = _make_proc(b"", returncode=1, stderr=b"boom")

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RuntimeError, match="exit 1"):
            await run_research(term="foo", vault_root=tmp_path)


@pytest.mark.asyncio
async def test_subprocess_timeout_raises(tmp_path: Path) -> None:
    proc = AsyncMock()
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    proc.kill = AsyncMock()
    proc.wait = AsyncMock()
    proc.returncode = -9

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RuntimeError, match="timed out"):
            await run_research(term="foo", vault_root=tmp_path)
    proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_unparseable_json_raises(tmp_path: Path) -> None:
    transcript = _stream_json(_final_text("not json at all"))
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        with pytest.raises(RuntimeError, match="no JSON"):
            await run_research(term="foo", vault_root=tmp_path)


@pytest.mark.asyncio
async def test_vault_read_ref_normalized_in_research_disposition(
    tmp_path: Path,
) -> None:
    note_path = tmp_path / "note.md"
    note_path.write_text("# note")
    transcript = _stream_json(
        _tool_use("t1", "Read", file_path=str(note_path)),
        _tool_result("t1"),
        _final_text(
            json.dumps(
                {
                    "disposition": "research",
                    "reason": "publicly-researchable",
                    "summary": "x",
                    "claims": [
                        {
                            "text": "claim from vault",
                            "source_refs": ["vault:note.md"],
                        }
                    ],
                }
            )
        ),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await run_research(term="foo", vault_root=tmp_path)

    assert result.disposition == "research"
    assert result.note is not None
    assert [c.text for c in result.note.claims] == ["claim from vault"]
