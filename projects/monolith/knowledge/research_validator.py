"""Sonnet-driven per-claim research validator (claude CLI subprocess).

Mirrors gap_classifier.py's subprocess pattern: Claude Max ToS-compliant,
HOME=/tmp env override, asyncio.wait_for timeout, stderr capture on
non-zero exit. Output is structured JSON parsed into ValidatedResearch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from knowledge.research_agent import ResearchNote, SourceEntry

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "sonnet-4-6@v1"

_VALIDATE_TIMEOUT_SECS = 180
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


_VALIDATOR_PROMPT = """\
You are validating a research note against the sources that were retrieved
during research. For each claim in the note, decide one of:

- **supported**: at least one source clearly substantiates the claim.
- **unsupported**: no source substantiates the claim. Treat hedged
  language ("may", "might", "is sometimes") strictly — if the source
  doesn't directly support it, mark unsupported.
- **speculative**: the source touches on the topic but doesn't actually
  back the claim as stated.

Respond with JSON ONLY, in this shape:

```json
{{"claims": [
  {{"text": "<claim text>", "verdict": "supported|unsupported|speculative", "reason": "<one sentence>"}}
]}}
```

Do not include any text outside the JSON block.

## Research note

Summary: {summary}

Claims:
{claims}

## Sources retrieved during research

{sources}
"""


Verdict = Literal["supported", "unsupported", "speculative"]


@dataclass(frozen=True)
class ValidatedClaim:
    text: str
    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class ValidatedResearch:
    claims: list[ValidatedClaim] = field(default_factory=list)
    timed_out: bool = False
    parse_error: Optional[str] = None
    duration_ms: int = 0

    @property
    def all_unsupported(self) -> bool:
        if not self.claims:
            return True
        return all(c.verdict != "supported" for c in self.claims)


def _format_claims(note: ResearchNote) -> str:
    return "\n".join(f"- {c.text}" for c in note.claims) or "(none)"


def _format_sources(sources: list[SourceEntry]) -> str:
    if not sources:
        return "(none)"
    lines = []
    for s in sources:
        if s.tool == "web_fetch":
            lines.append(
                f"- web_fetch: {s.url} (content_hash={s.content_hash}, "
                f"fetched_at={s.fetched_at}, skipped={s.skipped_reason})"
            )
        elif s.tool == "search_knowledge":
            lines.append(
                f"- search_knowledge: query={s.query!r}, note_ids={s.note_ids}"
            )
        elif s.tool == "web_search":
            lines.append(
                f"- web_search: query={s.query!r}, result_urls={s.result_urls}"
            )
    return "\n".join(lines)


async def validate_research(
    *,
    note: ResearchNote,
    sources: list[SourceEntry],
    claude_bin: str = "claude",
) -> ValidatedResearch:
    """Run Sonnet against (note, sources) and parse per-claim verdicts."""
    prompt = _VALIDATOR_PROMPT.format(
        summary=note.summary,
        claims=_format_claims(note),
        sources=_format_sources(sources),
    )

    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        claude_bin,
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        "sonnet",
        "-p",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "HOME": "/tmp"},
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_VALIDATE_TIMEOUT_SECS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "research_validator: subprocess timed out after %ds",
            _VALIDATE_TIMEOUT_SECS,
        )
        return ValidatedResearch(timed_out=True, duration_ms=duration_ms)

    duration_ms = int((time.monotonic() - start) * 1000)
    if proc.returncode != 0:
        logger.warning(
            "research_validator: subprocess exit=%d; stderr=%s",
            proc.returncode,
            stderr.decode(errors="replace")[:300],
        )
        return ValidatedResearch(
            parse_error=f"exit {proc.returncode}", duration_ms=duration_ms
        )

    parsed = _parse_validator_response(stdout.decode(errors="replace"))
    if parsed is None:
        return ValidatedResearch(
            parse_error="no JSON block found", duration_ms=duration_ms
        )

    try:
        claims = [
            ValidatedClaim(
                text=c["text"], verdict=c["verdict"], reason=c.get("reason", "")
            )
            for c in parsed.get("claims", [])
            if c.get("verdict") in ("supported", "unsupported", "speculative")
        ]
    except (KeyError, TypeError) as e:
        return ValidatedResearch(
            parse_error=f"malformed claims: {e}", duration_ms=duration_ms
        )

    return ValidatedResearch(claims=claims, duration_ms=duration_ms)


def _parse_validator_response(text: str) -> dict | None:
    """Extract the first JSON object from Claude's response.

    Tolerates prose preambles, fenced ```json blocks, and trailing prose.
    """
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
