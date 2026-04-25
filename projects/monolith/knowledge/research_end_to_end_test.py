"""End-to-end integration test for the external research pipeline.

Mocks at the LLM boundaries (Qwen agent run, Sonnet validator) but uses
real DB state, real vault file writes, and the real research handler.
Exercises the full state-machine transition from classified -> committed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Gap
from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_handler import research_gaps_handler
from knowledge.research_validator import ValidatedClaim, ValidatedResearch


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


@pytest.mark.asyncio
async def test_full_research_cycle_lands_validated_raw(session, tmp_path):
    """classified -> committed: validated note lands in _inbox/research/."""
    session.add(
        Gap(
            term="merkle-tree",
            note_id="merkle-tree",
            gap_class="external",
            state="classified",
            pipeline_version="test",
        )
    )
    session.commit()

    fake_note = ResearchNote(
        summary="A merkle tree is a hash-chained tree.",
        claims=[Claim(text="Merkle trees hash pairs of children.")],
    )
    fake_sources = [
        SourceEntry(
            tool="web_fetch",
            url="https://example.com/m",
            content_hash="sha256:abc",
            fetched_at="2026-04-25T09:00:00Z",
        )
    ]
    fake_validated = ValidatedResearch(
        claims=[
            ValidatedClaim(
                text="Merkle trees hash pairs of children.",
                verdict="supported",
                reason="from example.com/m",
            ),
        ]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, fake_sources)),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "merkle-tree")).scalar_one()
    assert gap.state == "committed"
    assert gap.research_attempts == 0  # no attempts burned on success

    raw = tmp_path / "_inbox" / "research" / "merkle-tree.md"
    assert raw.is_file()
    text = raw.read_text()
    assert "type: research" in text
    assert "Merkle trees hash pairs of children" in text
    assert "https://example.com/m" in text
