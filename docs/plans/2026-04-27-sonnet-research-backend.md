# Sonnet Research Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Qwen-driven research agent + Sonnet validator with a single Sonnet researcher that uses Claude's native tools (Read, Glob, Grep, WebSearch, WebFetch). Replace the Sonnet-on-Sonnet second-pass validator with a harness-side mechanical citation check that parses `claude --print --output-format stream-json` audit trails.

**Architecture:**

- Single `claude --print --output-format stream-json --model sonnet --allowedTools "Read,Glob,Grep,WebSearch,WebFetch" -p <prompt>` subprocess, `cwd=vault_root` so Read/Glob/Grep are scoped to the user's notes (matches `gardener.py` pattern).
- Sonnet first **triages** the gap (research / personal / discard), then conditionally produces a `ResearchNote` with claims that include `source_refs` (URLs or `vault:<path>`). See "Plan amendment" below for the disposition trichotomy and per-disposition handler routing.
- Harness parses the stream-json transcript to extract the audit trail of tool calls Sonnet _actually_ invoked, then drops any claim whose `source_refs` aren't in the audit trail. No second LLM call.
- `research_validator.py` and `research_tools.py` are **deleted**, not refactored.
- Frontmatter field renamed `qwen_model`/`sonnet_model` → `agent_model: sonnet`.

**Tech Stack:** Python 3.12, asyncio, `claude` CLI subprocess, pytest + pytest-asyncio. No new pip dependencies; the `pydantic_ai` dep stays because `chat/agent.py` still uses it.

**Engineering principles:** TDD (test-first per task), DRY, YAGNI, frequent commits. See `superpowers:test-driven-development` for the discipline. Don't run tests locally — push and watch CI per `CLAUDE.md`.

---

## Pre-flight

Worktree already cut at `/tmp/claude-worktrees/sonnet-research-backend` from `origin/main`. Branch: `feat/sonnet-research-backend`.

All file paths below are relative to that worktree root. **Never `cd ~/repos/homelab` during execution** — it auto-fetches and is for reads only.

---

## Plan amendment 2026-04-27: triage step inside the Sonnet researcher

After Task 1 landed, we agreed to add a first-pass triage inside the Sonnet subprocess. Rationale: the upstream `gap_classifier.py` only sees a stub's frontmatter (id, title, referenced_by) when it classifies, while the new researcher has full Read/Glob/Grep access to the vault — so it can catch upstream mis-classifications and skip wasted research runs. This refinement lands in Tasks 2/4/6; Tasks 1, 3, 5, 7, 8 are unchanged.

### Disposition trichotomy

Sonnet emits a top-level `disposition` before any claim work:

```json
{
  "disposition": "research" | "personal" | "discard",
  "reason": "<one sentence>",
  "summary": "...",        // only when disposition == "research"
  "claims": [...]           // only when disposition == "research"
}
```

### Per-disposition handler routing

| Disposition | Meaning                                                       | Handler action                                                                                                                                                                                                                                       |
| ----------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `research`  | External-researchable; here are the claims                    | Run mechanical citation filter against audit trail. If 0 surviving claims → quarantine path (existing). Else write `_inbox/research/<slug>.md` and set `gap.state = "committed"`.                                                                    |
| `personal`  | Sonnet found this is actually personal / only Joe can resolve | Set `gap.gap_class = "internal"`, `gap.state = "classified"`. **No vault file written.** The flipped `gap_class` is the marker — existing internal-gap workflow surfaces it. `research_attempts` NOT bumped (this isn't a research-budget consumer). |
| `discard`   | Irrelevant / typo / already-defined / not worth researching   | Set `gap.gap_class = "parked"`, `gap.state = "parked"`. **No vault file written.** Reconciler / tombstoning process handles cleanup. Terminal — does NOT consume one of the 3 retry attempts.                                                        |

### Decisions locked

1. **`personal` → `gap_class = internal`** (reuse existing type; no new state machine value).
2. **`discard` → state-only update** (no quarantine file, no forensic marker; reconciler tombstones it via the existing process).
3. **`discard` is terminal** (does not increment `research_attempts`; the 3-strikes-and-park budget is reserved for citation-failure quarantines from the `research` path).

### Tasks affected

- **Task 2 (research_agent rewrite):** prompt gains a triage section; output JSON gains `disposition` and `reason`; `run_research` returns `(disposition, note, sources, reason)` (or a wrapper dataclass). Tests cover all three dispositions plus the citation-filter case.
- **Task 4 (research_handler):** routes on `disposition` first. The `research` branch is what was already in the plan; `personal` and `discard` are new state-update branches.
- **Task 6 (e2e test):** three end-to-end paths instead of two.

Tasks 3 (writer), 5 (deletes), 7 (TTL comment), 8 (PR) are unchanged.

---

## Task 1: Audit-trail parser (leaf module, TDD)

A small pure module that turns `claude --print --output-format stream-json` stdout into the set of "valid source_refs" — i.e. things Sonnet actually retrieved. This module has no other dependencies; it can land first and be unit-tested in isolation.

**Files:**

- Create: `projects/monolith/knowledge/research_audit_trail.py`
- Create: `projects/monolith/knowledge/research_audit_trail_test.py`
- Modify: `projects/monolith/BUILD` (add new `py_test` target — see Task 1.6)

### Step 1.1: Reference the stream-json shape

Each line of stream-json stdout is a JSON object. The shapes we care about (from real `claude --print --output-format stream-json` output — verify by spawning a small test invocation if uncertain):

```jsonl
{"type":"system","subtype":"init","session_id":"...","tools":[...]}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_01","name":"WebFetch","input":{"url":"https://example.com/post","prompt":"extract main content"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_01","content":[{"type":"text","text":"..."}],"is_error":false}]}}
{"type":"assistant","message":{"content":[{"type":"text","text":"{\"summary\": \"...\", \"claims\": [...]}"}]}}
{"type":"result","subtype":"success","is_error":false,"result":"{\"summary\": ...}"}
```

We only care about successful `tool_use` invocations. A tool-call counts iff its paired `tool_result` came back with `is_error: false`. This module pairs them by `tool_use_id`/`tool_use_id` and emits the audit trail.

### Step 1.2: Write failing tests

Create `projects/monolith/knowledge/research_audit_trail_test.py`:

```python
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
    transcript = "not-json\n" + _ndjson(
        _tool_use("t7", "WebFetch", url="https://example.com/ok", prompt="..."),
        _tool_result("t7"),
    ) + "\n{partial...\n"
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
    # Recorded but their refs are not normally citable; the filter in
    # research_agent only consults trail.refs which excludes Glob/Grep.
    refs = {e.ref for e in trail.entries}
    assert refs == {"glob:**/*.md", "grep:kubernetes"}
    assert trail.refs == frozenset()  # not citable
```

### Step 1.3: Run tests to verify failure

Don't execute locally — the fail mode is "module does not exist yet". The tests serve as the spec.

### Step 1.4: Implement `research_audit_trail.py`

Create `projects/monolith/knowledge/research_audit_trail.py`:

```python
"""Parse `claude --print --output-format stream-json` transcripts into a
mechanically-verifiable audit trail of tool retrievals.

The research agent uses Claude's built-in tools (WebFetch/WebSearch/Read/
Glob/Grep). Each successful tool-use becomes an AuditEntry; the harness
filters research claims against ``trail.refs`` so a claim cannot cite a
URL the agent never actually fetched -- preserving the original "never
trust prose for citations" invariant from the Qwen-era design without
requiring a second LLM pass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# Tools whose successful invocations contribute citable refs.
# WebFetch -> URL, Read -> vault: or absolute path.
_CITABLE_TOOLS = frozenset({"WebFetch", "Read"})

# Tools whose invocations are recorded for debugging but do NOT yield
# citable refs (a claim cannot cite a search query).
_RECORDED_TOOLS = frozenset({"WebSearch", "Glob", "Grep"})


@dataclass(frozen=True)
class AuditEntry:
    tool: str
    ref: str  # URL for WebFetch, vault:path or absolute path for Read,
              # query for WebSearch, glob:/grep: prefix for Glob/Grep.


@dataclass(frozen=True)
class AuditTrail:
    entries: tuple[AuditEntry, ...]

    @property
    def refs(self) -> frozenset[str]:
        """The subset of entries whose refs are citable in a research claim.

        Only WebFetch URLs and Read paths qualify -- a claim can be backed
        by a fetched page or a vault note, but not by a search query.
        """
        return frozenset(e.ref for e in self.entries if e.tool in _CITABLE_TOOLS)


def parse_stream_json(transcript: str, *, vault_root: str | Path | None = None) -> AuditTrail:
    """Parse stream-json stdout into an AuditTrail.

    Tolerates malformed lines (logs and skips). Pairs tool_use with
    tool_result by ``tool_use_id``; only successful (is_error=False)
    pairs become entries. Unknown tools are silently dropped.
    """
    pending: dict[str, tuple[str, dict]] = {}
    successes: list[tuple[str, dict]] = []

    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("research_audit_trail: skipping malformed line: %r", line[:200])
            continue

        if event.get("type") == "assistant":
            for part in _iter_content(event):
                if part.get("type") == "tool_use":
                    pending[part["id"]] = (part.get("name", ""), part.get("input", {}) or {})
        elif event.get("type") == "user":
            for part in _iter_content(event):
                if part.get("type") != "tool_result":
                    continue
                tu_id = part.get("tool_use_id")
                if tu_id is None or part.get("is_error"):
                    pending.pop(tu_id, None)
                    continue
                call = pending.pop(tu_id, None)
                if call is not None:
                    successes.append(call)

    entries: list[AuditEntry] = []
    vault_str = str(vault_root) if vault_root is not None else None
    for name, args in successes:
        entry = _to_entry(name, args, vault_str)
        if entry is not None:
            entries.append(entry)
    return AuditTrail(entries=tuple(entries))


def _iter_content(event: dict) -> Iterable[dict]:
    msg = event.get("message") or {}
    content = msg.get("content") or []
    if isinstance(content, list):
        yield from (p for p in content if isinstance(p, dict))


def _to_entry(name: str, args: dict, vault_root: str | None) -> AuditEntry | None:
    if name == "WebFetch":
        url = args.get("url")
        return AuditEntry(tool="WebFetch", ref=url) if url else None
    if name == "WebSearch":
        query = args.get("query")
        return AuditEntry(tool="WebSearch", ref=query) if query else None
    if name == "Read":
        path = args.get("file_path")
        if not path:
            return None
        return AuditEntry(tool="Read", ref=_normalize_read_path(path, vault_root))
    if name == "Glob":
        pat = args.get("pattern")
        return AuditEntry(tool="Glob", ref=f"glob:{pat}") if pat else None
    if name == "Grep":
        pat = args.get("pattern")
        return AuditEntry(tool="Grep", ref=f"grep:{pat}") if pat else None
    return None


def _normalize_read_path(path: str, vault_root: str | None) -> str:
    """Map an absolute Read path to ``vault:<rel>`` if it lies inside vault_root,
    else return the path unchanged. Keeps citation refs short and stable."""
    if vault_root is None:
        return path
    try:
        rel = Path(path).resolve().relative_to(Path(vault_root).resolve())
    except (ValueError, OSError):
        return path
    return f"vault:{rel}"
```

### Step 1.5: Run tests to verify pass

The tests defined in Step 1.2 should now pass. Push to CI to confirm (per CLAUDE.md: no local test loop).

### Step 1.6: Add BUILD target

Modify `projects/monolith/BUILD` — add a new `py_test` target after `knowledge_research_tools_test` (around line 1950, but **place it in lexicographic order** matching existing targets):

```starlark
py_test(
    name = "knowledge_research_audit_trail_test",
    srcs = ["knowledge/research_audit_trail_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)
```

The new `research_audit_trail.py` source file is picked up by the existing glob `"knowledge/**/*.py"` in the `monolith_backend` library — no separate library target needed.

### Step 1.7: Format

```bash
cd /tmp/claude-worktrees/sonnet-research-backend && format
```

`format` runs gazelle, ruff, gofumpt, etc. — it will fix BUILD ordering and Python style.

### Step 1.8: Commit

```bash
git add projects/monolith/knowledge/research_audit_trail.py \
        projects/monolith/knowledge/research_audit_trail_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add stream-json audit-trail parser for research"
```

---

## Task 2: Rewrite `research_agent.py` as a Sonnet subprocess

This is the biggest single task. The new module replaces the Pydantic AI agent with a `claude --print` subprocess, defines fresh dataclasses (`Claim` now has `source_refs`, `SourceEntry` simplified to match the audit trail), and implements the mechanical citation filter.

**Files:**

- Modify: `projects/monolith/knowledge/research_agent.py` (full rewrite)
- Modify: `projects/monolith/knowledge/research_agent_test.py` (full rewrite)

### Step 2.1: Write failing tests

Replace the entire contents of `projects/monolith/knowledge/research_agent_test.py` with subprocess-mock tests in the style of `gap_classifier_test.py`. The tests cover:

- Subprocess called with the expected flags (`--print --output-format stream-json --model sonnet --allowedTools "Read,Glob,Grep,WebSearch,WebFetch"`, `cwd=vault_root`, `HOME=/tmp` env override).
- JSON ResearchNote successfully parsed.
- Claims whose `source_refs` are all in the audit trail → kept.
- Claims with a `source_ref` not in the audit trail → dropped.
- Claims with empty `source_refs` → dropped.
- All claims dropped → returned `note.claims == []` (handler quarantines on this).
- Subprocess timeout → raises `RuntimeError`.
- Subprocess non-zero exit → raises `RuntimeError`.
- JSON parse error → raises `RuntimeError`.

Full test file contents:

```python
"""Tests for the Sonnet-driven research agent (claude --print subprocess)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.research_agent import (
    AGENT_MODEL,
    Claim,
    ResearchNote,
    SONNET_ALLOWED_TOOLS,
    SourceEntry,
    run_research,
)


def _stream_json(*events: dict) -> bytes:
    return ("\n".join(json.dumps(e) for e in events) + "\n").encode()


def _tool_use(tu_id: str, name: str, **inp) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": tu_id, "name": name, "input": inp}]},
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
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


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
        _final_text(json.dumps({
            "summary": "x",
            "claims": [{"text": "y", "source_refs": ["https://example.com/a"]}],
        })),
    )
    proc = _make_proc(transcript)

    captured: dict = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        await run_research(term="foo", vault_root=tmp_path)

    args = captured["args"]
    assert args[0] == "claude"
    assert "--print" in args
    assert "--output-format" in args
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--dangerously-skip-permissions" in args
    assert "--model" in args
    assert args[args.index("--model") + 1] == AGENT_MODEL
    assert "--allowedTools" in args
    assert args[args.index("--allowedTools") + 1] == SONNET_ALLOWED_TOOLS
    assert captured["cwd"] == tmp_path
    assert captured["env"]["HOME"] == "/tmp"


@pytest.mark.asyncio
async def test_claims_with_valid_source_refs_kept(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
        _final_text(json.dumps({
            "summary": "term means X",
            "claims": [
                {"text": "Claim A", "source_refs": ["https://example.com/a"]},
            ],
        })),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        note, sources = await run_research(term="foo", vault_root=tmp_path)

    assert note.summary == "term means X"
    assert [c.text for c in note.claims] == ["Claim A"]
    assert sources == [SourceEntry(tool="WebFetch", ref="https://example.com/a")]


@pytest.mark.asyncio
async def test_claims_with_unsourced_refs_dropped(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebFetch", url="https://example.com/a", prompt="..."),
        _tool_result("t1"),
        _final_text(json.dumps({
            "summary": "x",
            "claims": [
                {"text": "kept", "source_refs": ["https://example.com/a"]},
                {"text": "dropped", "source_refs": ["https://example.com/never-fetched"]},
                {"text": "also dropped (no refs)", "source_refs": []},
            ],
        })),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        note, _ = await run_research(term="foo", vault_root=tmp_path)

    assert [c.text for c in note.claims] == ["kept"]


@pytest.mark.asyncio
async def test_all_claims_dropped_returns_empty_claims(tmp_path: Path) -> None:
    transcript = _stream_json(
        _tool_use("t1", "WebSearch", query="foo"),  # search only, no fetches
        _tool_result("t1"),
        _final_text(json.dumps({
            "summary": "x",
            "claims": [{"text": "unsupported", "source_refs": ["https://hallucinated.example"]}],
        })),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        note, _ = await run_research(term="foo", vault_root=tmp_path)

    assert note.claims == []


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
async def test_vault_read_ref_normalized(tmp_path: Path) -> None:
    note_path = tmp_path / "note.md"
    note_path.write_text("# note")
    transcript = _stream_json(
        _tool_use("t1", "Read", file_path=str(note_path)),
        _tool_result("t1"),
        _final_text(json.dumps({
            "summary": "x",
            "claims": [{"text": "claim from vault", "source_refs": ["vault:note.md"]}],
        })),
    )
    proc = _make_proc(transcript)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        note, _ = await run_research(term="foo", vault_root=tmp_path)

    assert [c.text for c in note.claims] == ["claim from vault"]
```

### Step 2.2: Implement the new `research_agent.py`

Replace the entire contents of `projects/monolith/knowledge/research_agent.py`:

```python
"""Sonnet-driven research agent (claude --print subprocess).

Replaces the Qwen+Pydantic-AI agent and the separate Sonnet validator.
A single ``claude --print --output-format stream-json`` invocation
researches a single term using Claude's built-in WebSearch/WebFetch/
Read/Glob/Grep tools, and returns a JSON ``ResearchNote``.

The harness then runs a *mechanical* citation check: each claim must
cite at least one source the agent actually retrieved (per the
stream-json audit trail). Claims with no retrieved sources are dropped;
the handler quarantines a research run that produces zero surviving
claims.

This preserves the original "never trust prose for citations" invariant
without a second LLM pass -- which is redundant once both stages run on
Sonnet (same model, same blind spots).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from knowledge.research_audit_trail import AuditTrail, parse_stream_json

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "research-pipeline@v2"

# Read from env so the model can be swapped (e.g. claude-sonnet-4-6 ->
# claude-sonnet-4-7) without a code change. ``sonnet`` is the alias for
# the latest Sonnet release.
AGENT_MODEL = os.getenv("CLAUDE_RESEARCH_MODEL", "sonnet")

SONNET_ALLOWED_TOOLS = "Read,Glob,Grep,WebSearch,WebFetch"

_RESEARCH_TIMEOUT_SECS = 600  # 10min cap for a full Sonnet research run
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


_RESEARCH_PROMPT = """\
You are a research agent for a knowledge graph. Your job is to research a
single term -- referenced in the user's vault but not yet defined -- and
produce a structured ResearchNote.

The user's vault is mounted at the current working directory. Files are
markdown notes; their frontmatter includes ``id`` and ``title``.

## Tools

- **Read / Glob / Grep** -- inspect the user's existing vault notes.
  Use these FIRST. The user's prior thinking is more trusted than any
  web source.
- **WebSearch(query)** -- search the open web. Returns titles + snippets.
- **WebFetch(url)** -- fetch a single URL's content. Use this AFTER
  WebSearch picks a candidate -- snippets alone are not enough to
  substantiate claims.

## Output

After research, emit JSON ONLY (no surrounding prose, no fences) in
this shape:

{{
  "summary": "<3-5 sentences explaining the term>",
  "claims": [
    {{
      "text": "<one factual claim about the term>",
      "source_refs": [
        "<url that you actually WebFetch'd>",
        "<vault:relative/path/to/note.md that you actually Read>"
      ]
    }}
  ]
}}

## Rules

- Every claim MUST list at least one ``source_ref`` in ``source_refs``,
  AND that ref MUST be either:
  - a URL you actually fetched with WebFetch, or
  - the literal string ``vault:<path>`` where ``<path>`` is the path
    you Read, relative to the working directory.
- The harness verifies refs against your tool-call audit trail. Claims
  whose refs were never retrieved are dropped automatically -- so do
  not invent citations.
- Quality over quantity: 3 strong claims is better than 8 weak ones.
- Do NOT include any prose outside the JSON object.

## Term to research

{term}

This term appears as an unresolved [[wikilink]] in the user's vault.
Use Read/Glob/Grep on the vault first, then WebSearch + WebFetch for
external context.
"""


@dataclass(frozen=True)
class Claim:
    text: str
    source_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResearchNote:
    summary: str
    claims: list[Claim] = field(default_factory=list)


@dataclass(frozen=True)
class SourceEntry:
    tool: str
    ref: str


async def run_research(
    *,
    term: str,
    vault_root: Path,
    claude_bin: str = "claude",
) -> tuple[ResearchNote, list[SourceEntry]]:
    """Spawn the Sonnet research subprocess and return (note, sources).

    Returns the post-filter note: claims whose source_refs are not in
    the audit trail have already been removed. The handler quarantines
    when ``note.claims == []``.

    Raises ``RuntimeError`` on infra failures (timeout, non-zero exit,
    no JSON found) -- the handler reverts state without bumping
    ``research_attempts`` in those cases.
    """
    prompt = _RESEARCH_PROMPT.format(term=term)
    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        claude_bin,
        "--print",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",  # required by stream-json output
        "--model",
        AGENT_MODEL,
        "--allowedTools",
        SONNET_ALLOWED_TOOLS,
        "-p",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=vault_root,
        # HOME=/ in the container (non-root uid 65532) is not writable, so
        # claude cannot create ~/.claude/ and exits silently with code 0.
        # Mirrors gardener.py / gap_classifier.py.
        env={**os.environ, "HOME": "/tmp"},
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_RESEARCH_TIMEOUT_SECS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"research_agent: claude timed out after {_RESEARCH_TIMEOUT_SECS}s"
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(
            f"research_agent: claude exit {proc.returncode}: "
            f"{stderr.decode(errors='replace')[:300]}"
        )

    transcript = stdout.decode(errors="replace")
    trail = parse_stream_json(transcript, vault_root=vault_root)
    note = _parse_research_note(transcript)
    filtered = _filter_claims(note, trail)

    sources = _audit_to_sources(trail)
    logger.info(
        "research_agent: term=%s claims_emitted=%d claims_kept=%d duration_ms=%d",
        term,
        len(note.claims),
        len(filtered.claims),
        duration_ms,
    )
    return filtered, sources


def _parse_research_note(transcript: str) -> ResearchNote:
    """Extract the JSON block from the stream-json transcript.

    The final assistant text message carries the JSON. Tolerates fenced
    blocks and trailing prose by extracting the first ``{...}`` span.
    """
    # Walk the transcript for the last assistant text part -- that's the
    # final answer. Falls back to a regex if the structured walk yields
    # nothing (defensive).
    candidate: str | None = None
    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for part in (event.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    candidate = part.get("text") or candidate
        elif event.get("type") == "result":
            result_text = event.get("result")
            if isinstance(result_text, str):
                candidate = result_text

    if candidate is None:
        raise RuntimeError("research_agent: no assistant text found in transcript")

    match = _JSON_BLOCK_RE.search(candidate)
    if match is None:
        raise RuntimeError("research_agent: no JSON block in final assistant text")

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"research_agent: malformed JSON: {e}") from e

    summary = str(data.get("summary", "")).strip()
    raw_claims = data.get("claims") or []
    claims = [
        Claim(
            text=str(c.get("text", "")).strip(),
            source_refs=tuple(str(r) for r in (c.get("source_refs") or [])),
        )
        for c in raw_claims
        if isinstance(c, dict) and c.get("text")
    ]
    return ResearchNote(summary=summary, claims=claims)


def _filter_claims(note: ResearchNote, trail: AuditTrail) -> ResearchNote:
    """Drop claims whose source_refs are not in the audit trail."""
    valid = trail.refs
    kept = [
        c for c in note.claims
        if c.source_refs and any(r in valid for r in c.source_refs)
    ]
    return ResearchNote(summary=note.summary, claims=kept)


def _audit_to_sources(trail: AuditTrail) -> list[SourceEntry]:
    """Project the audit trail into the SourceEntry shape used by the writer."""
    return [SourceEntry(tool=e.tool, ref=e.ref) for e in trail.entries]
```

### Step 2.3: Push to CI to verify tests pass

Don't run locally. Per CLAUDE.md, push and watch CI.

### Step 2.4: Commit (DO NOT push yet — we'll push after the whole feature is wired)

```bash
git add projects/monolith/knowledge/research_agent.py \
        projects/monolith/knowledge/research_agent_test.py
git commit -m "feat(knowledge): rewrite research agent as Sonnet subprocess"
```

---

## Task 3: Simplify `research_writer.py`

The writer no longer needs the `qwen_model`/`sonnet_model` split or the `validator_version` field. The `quarantine` writer no longer takes a `ValidatedResearch` (it doesn't exist anymore) — it just writes the post-filter `ResearchNote` and the audit trail.

**Files:**

- Modify: `projects/monolith/knowledge/research_writer.py`
- Modify: `projects/monolith/knowledge/research_writer_test.py` (full rewrite)

### Step 3.1: Write failing tests

Replace `projects/monolith/knowledge/research_writer_test.py`:

```python
"""Tests for the vault writers (research raws and quarantine drafts)."""

from __future__ import annotations

from pathlib import Path

import yaml

from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_writer import quarantine, write_research_raw


def _read_fm(path: Path) -> dict:
    text = path.read_text()
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def test_write_research_raw_minimal(tmp_path: Path) -> None:
    out = write_research_raw(
        vault_root=tmp_path,
        slug="foo",
        title="Foo",
        summary="A short summary.",
        supported_claims=[Claim(text="Foo is a thing.", source_refs=("https://example.com/a",))],
        sources=[SourceEntry(tool="WebFetch", ref="https://example.com/a")],
        agent_model="sonnet",
        researched_at="2026-04-27T12:00:00Z",
    )
    fm = _read_fm(out)
    assert fm["type"] == "research"
    assert fm["agent_model"] == "sonnet"
    assert fm["pipeline_version"] == "research-pipeline@v2"
    assert fm["claims_supported"] == 1
    assert fm["sources"] == [{"tool": "WebFetch", "ref": "https://example.com/a"}]
    assert "## Summary" in out.read_text()
    assert "Foo is a thing." in out.read_text()


def test_quarantine_writes_failed_research(tmp_path: Path) -> None:
    note = ResearchNote(
        summary="x", claims=[Claim(text="unsupported", source_refs=("https://a",))]
    )
    out = quarantine(
        vault_root=tmp_path,
        slug="foo",
        attempt=2,
        draft_note=note,
        sources=[SourceEntry(tool="WebSearch", ref="foo")],
        agent_model="sonnet",
        researched_at="2026-04-27T12:00:00Z",
    )
    fm = _read_fm(out)
    assert fm["type"] == "failed_research"
    assert fm["attempt"] == 2
    assert fm["agent_model"] == "sonnet"
    assert "## Claims" in out.read_text()
    assert "## Claims (Qwen)" not in out.read_text()
```

### Step 3.2: Update `research_writer.py`

```python
"""Vault writers for research raws and failed-research quarantine files.

Both writers produce idempotent, byte-stable markdown with YAML frontmatter
suitable for raw_ingest pickup. The schema of the frontmatter is the
ground-truth provenance for every atom that gets committed downstream.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from knowledge.research_agent import (
    PIPELINE_VERSION,
    Claim,
    ResearchNote,
    SourceEntry,
)

INBOX_RESEARCH_DIR = "_inbox/research"
FAILED_RESEARCH_DIR = "_failed_research"


def _source_to_fm(s: SourceEntry) -> dict[str, Any]:
    return {k: v for k, v in asdict(s).items() if v not in (None, [], "")}


def _yaml_dump(fm: dict) -> str:
    return yaml.dump(fm, default_flow_style=False, sort_keys=False)


def write_research_raw(
    *,
    vault_root: Path,
    slug: str,
    title: str,
    summary: str,
    supported_claims: list[Claim],
    sources: list[SourceEntry],
    agent_model: str,
    researched_at: str,
) -> Path:
    """Write the post-filter research raw to ``_inbox/research/<slug>.md``."""
    out_dir = vault_root / INBOX_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    fm = {
        "type": "research",
        "id": slug,
        "title": f"Research note: {title}",
        "derived_from_gap": slug,
        "agent_model": agent_model,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sources": [_source_to_fm(s) for s in sources],
        "claims_supported": len(supported_claims),
    }

    body_lines = [f"## Summary\n\n{summary}\n", "## Supported claims"]
    for c in supported_claims:
        refs = ", ".join(c.source_refs)
        body_lines.append(f"- {c.text} _[{refs}]_")
    body_lines.append("")
    body_lines.append("## Sources")
    for s in sources:
        body_lines.append(f"- {s.tool}: {s.ref}")

    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path


def quarantine(
    *,
    vault_root: Path,
    slug: str,
    attempt: int,
    draft_note: ResearchNote,
    sources: list[SourceEntry],
    agent_model: str,
    researched_at: str,
) -> Path:
    """Write a fully-rejected research draft to ``_failed_research/<slug>-<N>.md``.

    A draft is "rejected" when the post-filter claim list is empty -- i.e.
    no claim cited a source the agent actually retrieved. We persist the
    pre-filter note for forensics so we can see what Sonnet *tried* to
    say even though the citations didn't check out.
    """
    out_dir = vault_root / FAILED_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}-{attempt}.md"

    fm = {
        "type": "failed_research",
        "id": f"{slug}-{attempt}",
        "derived_from_gap": slug,
        "attempt": attempt,
        "agent_model": agent_model,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sources_attempted": [_source_to_fm(s) for s in sources],
    }

    body_lines = [
        f"# Failed research draft (attempt {attempt})",
        "",
        "## Summary",
        "",
        draft_note.summary,
        "",
        "## Claims",
    ]
    for c in draft_note.claims:
        refs = ", ".join(c.source_refs) if c.source_refs else "(no refs)"
        body_lines.append(f"- {c.text} _[{refs}]_")
    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path
```

### Step 3.3: Commit

```bash
git add projects/monolith/knowledge/research_writer.py \
        projects/monolith/knowledge/research_writer_test.py
git commit -m "refactor(knowledge): simplify research_writer to single-agent shape"
```

---

## Task 4: Simplify `research_handler.py`

The handler now has one LLM call instead of two. The `validator_failure` and `all_unsupported` branches collapse into "post-filter claims empty → quarantine".

**Files:**

- Modify: `projects/monolith/knowledge/research_handler.py`
- Modify: `projects/monolith/knowledge/research_handler_test.py` (full rewrite)

### Step 4.1: Write failing tests

Replace `projects/monolith/knowledge/research_handler_test.py`. Key cases:

- Happy path: agent returns claims → state transitions classified → researching → committed; `write_research_raw` called.
- Agent infra error (`RuntimeError`) → state reverts to classified; attempts NOT bumped; no write.
- All claims dropped (empty) → quarantine called; attempts++; state goes parked at >=3.
- Race lost (state already 'researching') → skip, no LLM call.
- Stuck-row recovery (state='researching' before tick) → swept back to 'classified'.
- Privacy-conservative re-assertion (gap_class != 'external' after lock) → skip.

The tests follow `research_handler_test.py`'s existing structure but mock `run_research` directly instead of the old `_run_research` indirection.

(I'll spell out the full test contents during implementation; the structure mirrors the existing 350-line test file closely. The key change is dropping all `validate_research`-related fixtures.)

### Step 4.2: Implement the new `research_handler.py`

```python
"""Scheduled-job handler for knowledge.research-gaps.

Every tick: pulls up to RESEARCH_BATCH_SIZE external+classified gaps,
runs the Sonnet research agent, transitions state per the design's state
machine. Infra failures (claude subprocess crash/timeout) revert state
without burning attempts. A research run with zero post-filter claims
quarantines the draft, bumps attempts, and parks at >=3.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from knowledge.models import Gap
from knowledge.research_agent import AGENT_MODEL, run_research
from knowledge.research_writer import quarantine, write_research_raw

logger = logging.getLogger(__name__)

RESEARCH_BATCH_SIZE = 3
RESEARCH_PARK_THRESHOLD = 3


async def research_gaps_handler(*, session: Session, vault_root: Path) -> None:
    """Run one tick of the external research pipeline."""
    # Recovery sweep -- see prior comment, unchanged.
    stuck = session.execute(
        Gap.__table__.update()
        .where(Gap.state == "researching")
        .values(state="classified")
    )
    if stuck.rowcount:
        logger.warning(
            "knowledge.research-gaps: recovered %d stuck 'researching' rows to "
            "'classified'",
            stuck.rowcount,
        )
    session.commit()

    candidates = (
        session.execute(
            select(Gap)
            .where(Gap.gap_class == "external", Gap.state == "classified")
            .order_by(Gap.id)
            .limit(RESEARCH_BATCH_SIZE)
        )
        .scalars()
        .all()
    )

    if not candidates:
        logger.info("knowledge.research-gaps: no candidates")
        return

    for gap in candidates:
        if gap.gap_class != "external":
            logger.warning(
                "knowledge.research-gaps: skipping non-external gap %s", gap.term
            )
            continue

        result = session.execute(
            Gap.__table__.update()
            .where(Gap.id == gap.id, Gap.state == "classified")
            .values(state="researching")
        )
        session.commit()
        if result.rowcount == 0:
            logger.info("knowledge.research-gaps: race lost for %s", gap.term)
            continue

        await _process_one(session=session, gap=gap, vault_root=vault_root)


async def _process_one(*, session: Session, gap: Gap, vault_root: Path) -> None:
    assert gap.note_id is not None, f"gap {gap.id} ({gap.term}) has no note_id"

    researched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        note, sources = await run_research(term=gap.term, vault_root=vault_root)
    except Exception:
        logger.exception(
            "knowledge.research-gaps: research failure on %s; reverting state",
            gap.term,
        )
        gap.state = "classified"
        session.commit()
        return

    if not note.claims:
        # Post-filter: no claim cited a source the agent actually retrieved.
        # Quarantine the draft for forensics and bump attempts.
        attempt = gap.research_attempts + 1
        try:
            quarantine(
                vault_root=vault_root,
                slug=gap.note_id,
                attempt=attempt,
                draft_note=note,
                sources=sources,
                agent_model=AGENT_MODEL,
                researched_at=researched_at,
            )
        except Exception:
            logger.exception(
                "knowledge.research-gaps: quarantine write failed for %s", gap.term
            )
            gap.state = "classified"
            session.commit()
            return

        gap.research_attempts = attempt
        gap.state = "parked" if attempt >= RESEARCH_PARK_THRESHOLD else "classified"
        session.commit()
        logger.info(
            "knowledge.research-gaps: rejected %s (attempt=%d, state=%s)",
            gap.term, attempt, gap.state,
        )
        return

    try:
        write_research_raw(
            vault_root=vault_root,
            slug=gap.note_id,
            title=gap.term,
            summary=note.summary,
            supported_claims=note.claims,
            sources=sources,
            agent_model=AGENT_MODEL,
            researched_at=researched_at,
        )
    except Exception:
        logger.exception(
            "knowledge.research-gaps: raw write failed for %s; reverting state",
            gap.term,
        )
        gap.state = "classified"
        session.commit()
        return

    gap.state = "committed"
    session.commit()
    logger.info(
        "knowledge.research-gaps: committed %s (claims=%d)",
        gap.term, len(note.claims),
    )
```

### Step 4.3: Commit

```bash
git add projects/monolith/knowledge/research_handler.py \
        projects/monolith/knowledge/research_handler_test.py
git commit -m "refactor(knowledge): simplify research_handler to single-LLM shape"
```

---

## Task 5: Delete validator + tools modules and BUILD targets

Now nothing imports them. Remove the dead code.

**Files to delete:**

- `projects/monolith/knowledge/research_validator.py`
- `projects/monolith/knowledge/research_validator_test.py`
- `projects/monolith/knowledge/research_tools.py`
- `projects/monolith/knowledge/research_tools_test.py`

**BUILD edits:**

- Remove `knowledge_research_validator_test` target (lines ~1966-1975)
- Remove `knowledge_research_tools_test` target (lines ~1940-1950)

### Step 5.1: Delete files

```bash
git rm projects/monolith/knowledge/research_validator.py \
       projects/monolith/knowledge/research_validator_test.py \
       projects/monolith/knowledge/research_tools.py \
       projects/monolith/knowledge/research_tools_test.py
```

### Step 5.2: Remove BUILD targets

Edit `projects/monolith/BUILD`: delete the two `py_test` blocks listed above.

### Step 5.3: Verify nothing still imports them

```bash
cd /tmp/claude-worktrees/sonnet-research-backend && \
  grep -rn "research_validator\|research_tools" projects/ --include="*.py" --include="BUILD*"
```

Expected: zero matches.

### Step 5.4: Commit

```bash
git add -A
git commit -m "refactor(knowledge): drop validator and Qwen tools modules"
```

---

## Task 6: Update `research_end_to_end_test.py`

This test mocked the validator + Qwen agent boundaries. Now there's only one boundary: `run_research`.

**Files:**

- Modify: `projects/monolith/knowledge/research_end_to_end_test.py`

### Step 6.1: Rewrite the end-to-end test

Replace mocks of `validate_research` and the old Qwen `_run_research` with a single mock of `knowledge.research_agent.run_research`. Assert that:

- A successful run produces a file under `_inbox/research/<slug>.md` with the expected frontmatter shape (including `agent_model: sonnet`).
- A run with zero post-filter claims produces a `_failed_research/<slug>-1.md`.

(Full file contents follow the existing test's structure; the simplification roughly halves its line count.)

### Step 6.2: Commit

```bash
git add projects/monolith/knowledge/research_end_to_end_test.py
git commit -m "test(knowledge): update research e2e test to single-agent shape"
```

---

## Task 7: Update `service.py` TTL comment

`projects/monolith/knowledge/service.py:38` says `# 20min lock-lease (Qwen + Sonnet round-trips can be slow)`. The new path has only Sonnet, so the comment is stale. The TTL itself (1200s) is still appropriate as an upper bound on a single Sonnet research run.

### Step 7.1: Update the comment

Edit line 38:

```python
_RESEARCH_TTL_SECS = 1200  # 20min lock-lease (Sonnet research runs can be slow with web tools)
```

### Step 7.2: Commit

```bash
git add projects/monolith/knowledge/service.py
git commit -m "docs(knowledge): update research TTL comment for single-agent shape"
```

---

## Task 8: Format, push, watch CI

### Step 8.1: Final format pass

```bash
cd /tmp/claude-worktrees/sonnet-research-backend && format
```

If `format` produces any changes, commit them:

```bash
git add -A
git commit -m "chore: apply format"
```

### Step 8.2: Push and create PR

```bash
git push -u origin feat/sonnet-research-backend
gh pr create --title "feat(knowledge): swap Qwen+validator research backend for Sonnet+mech-cite" \
  --body "$(cat <<'EOF'
## Summary

- Replace Qwen-driven research agent (Pydantic AI on llama.cpp) and the
  Sonnet-on-Sonnet second-pass validator with a single Sonnet
  ``claude --print`` subprocess that uses Claude's native WebFetch /
  WebSearch / Read / Glob / Grep tools.
- Citation rigor preserved by parsing ``--output-format stream-json`` for
  the audit trail of tools the agent actually invoked, then mechanically
  dropping any claim whose ``source_refs`` aren't in that trail. No
  second LLM call.
- Drops ``research_validator.py`` and ``research_tools.py`` (Qwen-era
  custom Pydantic AI tools).
- Frontmatter field ``qwen_model``/``sonnet_model`` -> ``agent_model:
  sonnet``. ``pipeline_version`` bumped to ``research-pipeline@v2``.

## Why

Sonnet validating Sonnet is "marking your own homework" -- same model,
same blind spots. The two-stage design earned its keep when stage 1 was
Qwen (a smaller, less reliable model whose outputs needed a stronger
grader). With Sonnet on both sides the second pass is mostly redundant
billing. The mechanical citation check captures the part that's actually
load-bearing.

## Test plan

- [ ] CI green
- [ ] After deploy: schedule next ``knowledge.research-gaps`` tick, watch
      logs for ``research_agent: term=... claims_emitted=N claims_kept=M``
- [ ] Verify a successful run lands a markdown file under
      ``_inbox/research/`` with ``agent_model: sonnet`` and at least one
      claim citing a real URL
- [ ] Verify the no-citations branch lands ``_failed_research/<slug>-1.md``
EOF
)"
```

### Step 8.3: Watch CI

```bash
gh pr checks <pr-number> --watch
```

Iterate on failures by reading logs via `mcp__buildbuddy__get_invocation` + `get_log` (per CLAUDE.md). **Quote the actual error before hypothesizing** -- do not blame infra without evidence.

---

## Post-merge verification

After the PR merges and ArgoCD syncs the monolith:

1. Confirm the new image is deployed: `kubectl get pod -n monolith -l app.kubernetes.io/component=backend -o jsonpath='{.items[*].spec.containers[*].image}'`.
2. Wait for the next `knowledge.research-gaps` scheduled tick (cadence per `knowledge/service.py`).
3. Check logs: `kubectl logs -n monolith <pod> | grep research_agent`. Expect lines with `claims_emitted=` and `claims_kept=`.
4. Inspect the vault for new `_inbox/research/*.md` files; confirm `agent_model: sonnet` in frontmatter and that every claim's bracketed `_[refs]_` actually appears in the `## Sources` section below it.
5. If the first runs all hit `claims_kept=0`, that's a signal Sonnet isn't citing fetched URLs the way the prompt expects -- iterate on the prompt rather than relaxing the mechanical check.

---

## Notes for the implementer

- **No local tests.** Per CLAUDE.md, push and watch CI. Do NOT run `pytest` from the workstation.
- **Verify the `--output-format stream-json` shape early.** If `--verbose` is required and missing, the CLI will error with a clear message; if the JSON event shape differs from what the parser assumes, the parser tests will catch it. Spawning one real `claude --print --output-format stream-json --verbose -p "say hi"` invocation locally is fine for one-shot shape verification; just don't loop on it.
- **Don't bump `Chart.yaml`.** This change is monolith-Python only -- no chart changes, no values.yaml changes.
- **Do not migrate existing research raws.** Old `_inbox/research/*.md` files keep their `qwen_model` field; the raw_ingest pipeline doesn't validate field names strictly.
- **PR review cadence:** one comprehensive review after the whole PR is up, per CLAUDE.md's multi-step plan rule. No per-task review dispatches.
