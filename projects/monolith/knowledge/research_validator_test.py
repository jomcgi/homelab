"""Tests for the Sonnet-driven per-claim research validator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_validator import (
    VALIDATOR_VERSION,
    ValidatedClaim,
    ValidatedResearch,
    validate_research,
)


@pytest.mark.asyncio
async def test_validate_research_parses_per_claim_verdicts():
    """Sonnet returns JSON; we parse it into ValidatedResearch."""
    note = ResearchNote(
        summary="X is Y.", claims=[Claim(text="X is Y."), Claim(text="X is Z.")]
    )
    sources = [SourceEntry(tool="web_fetch", url="https://example.com/x")]

    fake_stdout = json.dumps(
        {
            "claims": [
                {
                    "text": "X is Y.",
                    "verdict": "supported",
                    "reason": "directly stated in source",
                },
                {
                    "text": "X is Z.",
                    "verdict": "unsupported",
                    "reason": "no source mentions Z",
                },
            ]
        }
    ).encode()

    proc = AsyncMock()
    proc.communicate.return_value = (fake_stdout, b"")
    proc.returncode = 0
    with patch(
        "knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await validate_research(note=note, sources=sources)

    assert isinstance(result, ValidatedResearch)
    assert len(result.claims) == 2
    assert result.claims[0].verdict == "supported"
    assert result.claims[1].verdict == "unsupported"


@pytest.mark.asyncio
async def test_validate_research_handles_subprocess_timeout():
    """Subprocess timeout returns ValidatedResearch with empty claims (treated as all-unsupported upstream)."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    proc = AsyncMock()
    proc.communicate.side_effect = TimeoutError()
    proc.kill = AsyncMock()
    proc.wait = AsyncMock()
    proc.returncode = -9
    with patch(
        "knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc
    ):
        with patch(
            "knowledge.research_validator.asyncio.wait_for", side_effect=TimeoutError()
        ):
            result = await validate_research(note=note, sources=[])

    assert result.timed_out is True
    assert result.claims == []


@pytest.mark.asyncio
async def test_validate_research_handles_malformed_json():
    """A non-JSON Sonnet response is parsed leniently — first JSON block, or empty."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    fake_stdout = (
        b"Here are the verdicts:\n```json\n"
        + json.dumps(
            {"claims": [{"text": "X is Y.", "verdict": "supported", "reason": "ok"}]}
        ).encode()
        + b"\n```\nLet me know if you want anything else."
    )

    proc = AsyncMock()
    proc.communicate.return_value = (fake_stdout, b"")
    proc.returncode = 0
    with patch(
        "knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await validate_research(note=note, sources=[])

    assert len(result.claims) == 1
    assert result.claims[0].verdict == "supported"


@pytest.mark.asyncio
async def test_validate_research_handles_unparseable_response():
    """Total parse failure returns empty claims with parse_error set."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    proc = AsyncMock()
    proc.communicate.return_value = (b"I cannot help with that request.", b"")
    proc.returncode = 0
    with patch(
        "knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await validate_research(note=note, sources=[])

    assert result.parse_error is not None
    assert result.claims == []


def test_validated_research_all_unsupported_helper():
    """ValidatedResearch.all_unsupported is the upstream branch signal."""
    # VALIDATOR_VERSION is the public version stamp other modules consume.
    assert isinstance(VALIDATOR_VERSION, str) and VALIDATOR_VERSION

    none = ValidatedResearch(claims=[])
    assert none.all_unsupported is True

    all_un = ValidatedResearch(
        claims=[
            ValidatedClaim(text="x", verdict="unsupported", reason="r"),
            ValidatedClaim(text="y", verdict="speculative", reason="r"),
        ]
    )
    assert all_un.all_unsupported is True

    mixed = ValidatedResearch(
        claims=[
            ValidatedClaim(text="x", verdict="supported", reason="r"),
            ValidatedClaim(text="y", verdict="unsupported", reason="r"),
        ]
    )
    assert mixed.all_unsupported is False
