"""Tests for stream-json audit-trail parser."""

from __future__ import annotations

import json

from knowledge.research_audit_trail import (
    AuditEntry,
    AuditTrail,
    parse_stream_json,
)


def _ndjson(*objs: dict) -> str:
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def _tool_use(tu_id: str, name: str, **input_kwargs) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tu_id,
                    "name": name,
                    "input": input_kwargs,
                }
            ]
        },
    }


def _tool_result(tu_id: str, *, is_error: bool = False, text: str = "ok") -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tu_id,
                    "content": [{"type": "text", "text": text}],
                    "is_error": is_error,
                }
            ]
        },
    }


def test_webfetch_pair_yields_url_entry() -> None:
    transcript = _ndjson(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
    )
    trail = parse_stream_json(transcript)
    assert trail.entries == (AuditEntry(tool="WebFetch", ref="https://example.com/a"),)
    assert "https://example.com/a" in trail.refs


def test_websearch_pair_yields_query_entry() -> None:
    transcript = _ndjson(
        _tool_use("t2", "WebSearch", query="linkerd mtls"),
        _tool_result("t2"),
    )
    trail = parse_stream_json(transcript)
    assert trail.entries == (AuditEntry(tool="WebSearch", ref="linkerd mtls"),)


def test_read_pair_yields_vault_entry() -> None:
    transcript = _ndjson(
        _tool_use("t3", "Read", file_path="/vault/notes/foo.md"),
        _tool_result("t3"),
    )
    trail = parse_stream_json(transcript, vault_root="/vault")
    assert trail.entries == (AuditEntry(tool="Read", ref="vault:notes/foo.md"),)
    assert "vault:notes/foo.md" in trail.refs


def test_errored_tool_result_excluded() -> None:
    transcript = _ndjson(
        _tool_use("t4", "WebFetch", url="https://example.com/404", prompt="..."),
        _tool_result("t4", is_error=True),
    )
    trail = parse_stream_json(transcript)
    assert trail.entries == ()
    assert trail.refs == frozenset()


def test_unpaired_tool_use_excluded() -> None:
    transcript = _ndjson(
        _tool_use("t5", "WebFetch", url="https://example.com/orphan", prompt="..."),
    )
    trail = parse_stream_json(transcript)
    assert trail.entries == ()


def test_unknown_tool_ignored() -> None:
    transcript = _ndjson(
        _tool_use("t6", "Bash", command="whoami"),
        _tool_result("t6"),
    )
    trail = parse_stream_json(transcript)
    assert trail.entries == ()


def test_malformed_lines_tolerated() -> None:
    transcript = (
        "not-json\n"
        + _ndjson(
            _tool_use("t7", "WebFetch", url="https://example.com/ok", prompt="..."),
            _tool_result("t7"),
        )
        + "\n{partial...\n"
    )
    trail = parse_stream_json(transcript)
    assert trail.refs == frozenset({"https://example.com/ok"})


def test_outside_vault_read_recorded_as_absolute() -> None:
    """Read of a file outside the vault keeps its absolute path; tests assert
    we don't silently rewrite it to a misleading vault: prefix."""
    transcript = _ndjson(
        _tool_use("t8", "Read", file_path="/etc/hosts"),
        _tool_result("t8"),
    )
    trail = parse_stream_json(transcript, vault_root="/vault")
    assert trail.entries == (AuditEntry(tool="Read", ref="/etc/hosts"),)


def test_glob_grep_recorded_as_query_entries() -> None:
    """Glob/Grep are valid retrieval tools but their refs are query strings,
    not URLs/paths -- a claim cannot cite a Glob result; only the Read it
    triggered should be cited."""
    transcript = _ndjson(
        _tool_use("g1", "Glob", pattern="**/*.md"),
        _tool_result("g1"),
        _tool_use("g2", "Grep", pattern="kubernetes", path="/vault"),
        _tool_result("g2"),
    )
    trail = parse_stream_json(transcript, vault_root="/vault")
    refs = {e.ref for e in trail.entries}
    assert refs == {"glob:**/*.md", "grep:kubernetes"}
    assert trail.refs == frozenset()  # not citable
