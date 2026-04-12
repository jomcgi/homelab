"""Tests for knowledge CLI subcommands.

Uses FastAPI TestClient to exercise the full round-trip:
CLI command -> httpx call -> FastAPI handler -> response -> formatted output.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from knowledge.gardener import Gardener
from knowledge.models import AtomRawProvenance, RawInput
from main import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def session():
    from sqlmodel import Session, SQLModel, create_engine
    from sqlmodel.pool import StaticPool

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
        with Session(engine) as s:
            yield s
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


@pytest.fixture(autouse=True)
def _patch_fastapi(session):
    """Point the CLI's httpx calls at the FastAPI TestClient.

    FastAPI's TestClient is httpx-compatible, so we patch knowledge._client
    to return it directly. We also patch get_cf_token to avoid reading real
    cloudflared files.
    """
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    from app.db import get_session

    fastapi_app.dependency_overrides[get_session] = lambda: session
    test_client = TestClient(fastapi_app)

    @contextmanager
    def _fake_client():
        yield test_client

    with (
        patch("knowledge._client", _fake_client),
        patch("knowledge.get_cf_token", return_value="fake-token"),
    ):
        yield

    fastapi_app.dependency_overrides.clear()


def _make_raw(session, *, raw_id="raw-1", path="raw/test.md", source="test"):
    raw = RawInput(
        raw_id=raw_id,
        path=path,
        source=source,
        content="test content",
        content_hash="abc123",
    )
    session.add(raw)
    session.commit()
    session.refresh(raw)
    return raw


def _make_dead_letter(session, raw, *, error="boom", retry_count=3):
    prov = AtomRawProvenance(
        raw_fk=raw.id,
        derived_note_id="failed",
        gardener_version="test-v1",
        error=error,
        retry_count=retry_count,
    )
    session.add(prov)
    session.commit()
    session.refresh(prov)
    return prov


class TestDeadLetters:
    def test_lists_dead_letters(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "dead-letters"])
        assert result.exit_code == 0
        assert "raw/test.md" in result.output
        assert "boom" in result.output

    def test_empty_list(self, runner, session):
        result = runner.invoke(app, ["knowledge", "dead-letters"])
        assert result.exit_code == 0
        assert "No dead letters" in result.output

    def test_json_output(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "dead-letters", "--json"])
        assert result.exit_code == 0
        assert '"items"' in result.output


class TestReplay:
    def test_replays_dead_letter(self, runner, session):
        raw = _make_raw(session)
        _make_dead_letter(session, raw, retry_count=Gardener._MAX_RETRIES)
        result = runner.invoke(app, ["knowledge", "replay", str(raw.id)])
        assert result.exit_code == 0
        assert "Replayed" in result.output

    def test_404_for_unknown(self, runner, session):
        result = runner.invoke(app, ["knowledge", "replay", "9999"])
        assert result.exit_code == 1
