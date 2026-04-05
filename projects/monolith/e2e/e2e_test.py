"""E2E integration tests for the monolith.

Tests run against real PostgreSQL 16 + pgvector. External services
(Discord, LLMs, SearXNG, vault) are mocked.
"""


def test_postgres_is_running(pg):
    """Smoke test: PostgreSQL is reachable and has pgvector."""
    from sqlalchemy import text
    from sqlmodel import create_engine

    engine = create_engine(pg.url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1
        # Verify pgvector extension is loaded
        has_vector = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        assert has_vector == 1
    engine.dispose()
