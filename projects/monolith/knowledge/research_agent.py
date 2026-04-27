"""Sonnet-driven research agent with first-pass triage.

Replaces the Qwen+Pydantic-AI agent and the separate Sonnet validator.
A single ``claude --print --output-format stream-json`` invocation:

  1. Triages the gap into one of three dispositions:
     - ``research``: external-researchable; produce claims with citations
     - ``personal``: actually personal/internal; bail and let the handler
       flip ``gap.gap_class = internal``
     - ``discard``: irrelevant / duplicate / not worth researching; bail
       and let the handler park the gap
  2. When ``research``, uses Claude's built-in WebSearch/WebFetch/Read/
     Glob/Grep tools to retrieve sources and emit a ``ResearchNote``.

The harness then runs a mechanical citation check (only on ``research``
disposition): each claim must cite at least one source the agent
actually retrieved (per the stream-json audit trail). Claims with no
retrieved sources are dropped; the handler quarantines a research run
that produces zero surviving claims.

Triage is a refinement of the upstream ``gap_classifier``, not a
replacement -- the classifier only sees stub frontmatter, while the
researcher has full vault access and can catch mis-classifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from knowledge.research_audit_trail import AuditTrail, parse_stream_json

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "research-pipeline@v2"

# Read from env so the model can be swapped (e.g. claude-sonnet-4-6 ->
# claude-sonnet-4-7) without a code change. ``sonnet`` is the alias for
# the latest Sonnet release.
AGENT_MODEL = os.getenv("CLAUDE_RESEARCH_MODEL", "sonnet")

SONNET_ALLOWED_TOOLS = "Read,Glob,Grep,WebSearch,WebFetch"

_RESEARCH_TIMEOUT_SECS = 600  # 10min cap for a full Sonnet research run

Disposition = Literal["research", "personal", "discard"]
_VALID_DISPOSITIONS: frozenset[str] = frozenset({"research", "personal", "discard"})


_RESEARCH_PROMPT = """\
You are a research agent for a knowledge graph. Your job is to triage and
optionally research a single term -- referenced in the user's vault but
not yet defined.

The user's vault is mounted at the current working directory. Files are
markdown notes; their frontmatter includes ``id`` and ``title``.

## Step 1: Triage

Use Read / Glob / Grep to inspect the vault first. Decide one of three
dispositions:

- **research**: The term is publicly-researchable (a concept, product,
  technique, etc.) and your vault inspection didn't reveal it's actually
  personal or already-defined. Continue to Step 2.
- **personal**: The term is personal to the user -- a friend's name, a
  shorthand for a private project, an emotional concept tied to their
  own life, etc. The web cannot answer this; only the user can.
- **discard**: The term is irrelevant (typo, formatting noise),
  duplicative of an existing well-defined concept in the vault, or
  otherwise not worth researching.

**Privacy-conservative default:** when in doubt between research and
personal, choose **personal**. Over-routing to the user is tolerated;
over-routing to the web is treated as a defect.

## Step 2: Research (only if disposition == "research")

Use WebSearch to find candidate sources, then WebFetch the URLs that
look most relevant. Snippets alone are not enough to substantiate
claims -- always WebFetch a page before citing it.

## Output

Emit JSON ONLY (no surrounding prose, no fences) in this exact shape:

{{
  "disposition": "research" | "personal" | "discard",
  "reason": "<one-sentence explanation of the disposition>",
  "summary": "<3-5 sentence summary>",
  "claims": [
    {{
      "text": "<one factual claim>",
      "source_refs": ["<url-you-WebFetch'd>", "vault:<path-you-Read>"]
    }}
  ]
}}

When ``disposition`` is ``"personal"`` or ``"discard"``:
- Omit ``summary`` and ``claims`` (or set them to ``null`` / ``[]``).
- Make ``reason`` informative -- what about your vault inspection led
  you to this verdict.

## Rules

- Every claim MUST list at least one ``source_ref`` that you actually
  retrieved with WebFetch (URL) or Read (``vault:<rel-path>``). The
  harness verifies refs against your tool-call audit trail; claims
  citing un-retrieved sources are dropped automatically.
- Quality over quantity: 3 strong claims beats 8 weak ones.
- No prose outside the JSON object. No fences. No commentary.

## Term to research

{term}

This term appears as an unresolved [[wikilink]] in the user's vault.
Triage first; research only if disposition is ``research``.
"""


@dataclass(frozen=True)
class Claim:
    text: str
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchNote:
    summary: str
    claims: list[Claim] = field(default_factory=list)


@dataclass(frozen=True)
class SourceEntry:
    tool: str
    ref: str


@dataclass(frozen=True)
class ResearchResult:
    """The complete result of one research run.

    ``note`` is populated only when ``disposition == "research"``. The
    handler routes on ``disposition`` -- the ``personal`` / ``discard``
    branches don't read ``note`` at all.

    ``raw_claims`` is Sonnet's emitted claims **before** the mechanical
    citation filter, populated only for ``disposition == "research"``.
    The handler uses it for quarantine forensics: when ``note.claims``
    is empty post-filter, ``raw_claims`` shows what Sonnet tried to say.
    """

    disposition: Disposition
    reason: str
    note: ResearchNote | None = None
    raw_claims: tuple[Claim, ...] = ()
    sources: tuple[SourceEntry, ...] = ()


async def run_research(
    *,
    term: str,
    vault_root: Path,
    claude_bin: str = "claude",
) -> ResearchResult:
    """Spawn the Sonnet research subprocess and return a ResearchResult.

    For ``disposition == "research"``, the returned ``note.claims`` is
    already post-filter -- claims whose source_refs are not in the audit
    trail have been dropped. The handler quarantines when ``note`` is
    populated but ``note.claims == []``.

    Raises ``RuntimeError`` on infra failures (timeout, non-zero exit,
    no JSON found, malformed JSON, invalid disposition value) -- the
    handler reverts state without bumping ``research_attempts`` in those
    cases.
    """
    prompt = _RESEARCH_PROMPT.format(term=term)
    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        claude_bin,
        "--print",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
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
    sources = tuple(SourceEntry(tool=e.tool, ref=e.ref) for e in trail.entries)

    parsed = _parse_response(transcript)
    disposition = parsed["disposition"]
    reason = parsed.get("reason") or ""

    if disposition != "research":
        logger.info(
            "research_agent: term=%s disposition=%s duration_ms=%d",
            term,
            disposition,
            duration_ms,
        )
        return ResearchResult(disposition=disposition, reason=reason, sources=sources)

    note_pre = _build_note(parsed)
    note_post = _filter_claims(note_pre, trail)
    logger.info(
        "research_agent: term=%s disposition=research "
        "claims_emitted=%d claims_kept=%d duration_ms=%d",
        term,
        len(note_pre.claims),
        len(note_post.claims),
        duration_ms,
    )
    return ResearchResult(
        disposition="research",
        reason=reason,
        note=note_post,
        raw_claims=tuple(note_pre.claims),
        sources=sources,
    )


def _parse_response(transcript: str) -> dict:
    """Extract and validate the JSON object from the stream-json transcript.

    Prefers the canonical ``result`` event when present; falls back to the
    last assistant text part. Validates that ``disposition`` is one of the
    three allowed values. Raises ``RuntimeError`` on any malformed input.
    """
    result_text: str | None = None
    last_assistant_text: str | None = None

    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "result":
            r = event.get("result")
            if isinstance(r, str):
                result_text = r
        elif etype == "assistant":
            for part in (event.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if text:
                        last_assistant_text = text

    candidate = result_text if result_text is not None else last_assistant_text
    if candidate is None:
        raise RuntimeError("research_agent: no JSON in transcript")

    block = _extract_json_block(candidate)
    if block is None:
        raise RuntimeError("research_agent: no JSON block in final text")

    try:
        data = json.loads(block)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"research_agent: malformed JSON: {e}") from e

    if not isinstance(data, dict):
        raise RuntimeError("research_agent: JSON is not an object")
    disposition = data.get("disposition")
    if disposition not in _VALID_DISPOSITIONS:
        raise RuntimeError(f"research_agent: invalid disposition {disposition!r}")
    return data


def _extract_json_block(s: str) -> str | None:
    """Extract the first balanced top-level JSON object from ``s``.

    Walks the string character-by-character, tracking brace depth while
    respecting JSON string-escape semantics. Returns ``None`` if no
    balanced object is found. More robust than a greedy/non-greedy regex
    when the candidate carries explanatory text around the JSON.
    """
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(s):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue  # stray closing brace before any opener; skip
            depth -= 1
            if depth == 0 and start != -1:
                return s[start : i + 1]
    return None


def _build_note(parsed: dict) -> ResearchNote:
    """Build a ResearchNote from the parsed JSON's summary + claims."""
    summary = str(parsed.get("summary") or "").strip()
    raw_claims = parsed.get("claims") or []
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
    """Drop claims with any unretrieved source_ref.

    A claim survives iff it has at least one source_ref AND **every**
    ref was actually retrieved by the agent (i.e. is in ``trail.refs``,
    which is WebFetch URLs + Read paths only -- queries are not citable).

    Stricter than "any ref valid" on purpose: a claim citing one real
    URL alongside a hallucinated one would otherwise survive and present
    the hallucinated URL as authoritative to downstream readers.
    """
    valid = trail.refs
    kept = [
        c
        for c in note.claims
        if c.source_refs and all(r in valid for r in c.source_refs)
    ]
    return ResearchNote(summary=note.summary, claims=kept)
