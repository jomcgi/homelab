"""Postgres data access layer for the knowledge schema."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, delete, select

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.links import Link
from knowledge.models import Chunk, Note, NoteLink
from shared.chunker import Chunk as ChunkPayload

logger = logging.getLogger(__name__)


class KnowledgeStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_indexed(self) -> dict[str, str]:
        result = self.session.execute(select(Note.path, Note.content_hash))
        return {path: ch for path, ch in result.all()}

    def upsert_note(
        self,
        *,
        note_id: str,
        path: str,
        content_hash: str,
        title: str,
        metadata: ParsedFrontmatter,
        chunks: list[ChunkPayload],
        vectors: list[list[float]],
        links: list[Link],
    ) -> None:
        # Wrap delete+insert in a SAVEPOINT so a mid-insert failure rolls
        # back the cascade deletes — the existing row is preserved even if
        # the caller never rolls back explicitly.
        with self.session.begin_nested():
            # Delete existing note and its dependents. Explicit cascade for
            # portability across Postgres and SQLite (which needs PRAGMA
            # foreign_keys=ON for FK cascades to fire).
            existing = self.session.execute(
                select(Note.id).where(Note.path == path)
            ).scalar_one_or_none()
            if existing is not None:
                self.session.execute(delete(Chunk).where(Chunk.note_fk == existing))
                self.session.execute(
                    delete(NoteLink).where(NoteLink.src_note_fk == existing)
                )
                self.session.execute(delete(Note).where(Note.id == existing))
                self.session.flush()

            note = Note(
                note_id=note_id,
                path=path,
                title=title,
                content_hash=content_hash,
                type=metadata.type,
                status=metadata.status,
                source=metadata.source,
                tags=metadata.tags,
                aliases=metadata.aliases,
                created_at=metadata.created,
                updated_at=metadata.updated,
                extra=metadata.extra,
                indexed_at=datetime.now(timezone.utc),
            )
            self.session.add(note)
            self.session.flush()

            for chunk, vector in zip(chunks, vectors, strict=True):
                self.session.add(
                    Chunk(
                        note_fk=note.id,
                        chunk_index=chunk["index"],
                        section_header=chunk["section_header"],
                        chunk_text=chunk["text"],
                        embedding=vector,
                    )
                )

            # Untyped body wikilinks -> kind='link'.
            for link in links:
                self.session.add(
                    NoteLink(
                        src_note_fk=note.id,
                        target_id=link.target,
                        target_title=link.display,
                        kind="link",
                        edge_type=None,
                    )
                )

            # Typed frontmatter edges -> kind='edge', edge_type=<key>.
            for edge_type, targets in metadata.edges.items():
                for target in targets:
                    self.session.add(
                        NoteLink(
                            src_note_fk=note.id,
                            target_id=target,
                            target_title=None,
                            kind="edge",
                            edge_type=edge_type,
                        )
                    )
            self.session.flush()

        self.session.commit()

    def search_notes(
        self,
        query_embedding: list[float],
        limit: int = 5,
        exclude_ids: list[str] | None = None,
    ) -> list[dict]:
        """Semantic search over notes using cosine similarity.

        Joins Note with Chunk, computes pgvector cosine_distance on
        Chunk.embedding, groups by note, and returns the best (minimum
        distance) chunk score per note as ``score = 1 - distance``.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding)
        best_score = (1 - func.min(distance)).label("score")

        stmt = (
            select(
                Note.note_id,
                Note.title,
                Note.path,
                best_score,
            )
            .join(Chunk, Chunk.note_fk == Note.id)
            .group_by(Note.id)
            .order_by(func.min(distance))
            .limit(limit)
        )

        if exclude_ids:
            stmt = stmt.where(Note.note_id.notin_(exclude_ids))

        rows = self.session.execute(stmt).all()
        return [
            {
                "note_id": row.note_id,
                "title": row.title,
                "path": row.path,
                "score": float(row.score),
            }
            for row in rows
        ]

    def search_notes_with_context(
        self,
        query_embedding: list[float],
        limit: int = 20,
        type_filter: str | None = None,
    ) -> list[dict]:
        """Semantic search returning type, tags, best chunk section + snippet.

        Powers the knowledge search overlay (ADR 003). Runs two SQL
        round-trips:

        1. Top-N notes ranked by ``best_score = 1 - min(cosine_distance)``
           across their chunks, with optional ``Note.type`` filter.
        2. A single batched ``SELECT DISTINCT ON (note_fk)`` to pick the
           best-matching chunk per top-N note — no N+1.

        Results are stitched in Python into dicts with keys:
        ``note_id, title, path, type, tags, score, section, snippet``.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding)
        best_score = (1 - func.min(distance)).label("score")

        notes_stmt = (
            select(
                Note.id,
                Note.note_id,
                Note.title,
                Note.path,
                Note.type,
                Note.tags,
                best_score,
            )
            .join(Chunk, Chunk.note_fk == Note.id)
            .group_by(Note.id)
            .order_by(func.min(distance))
            .limit(limit)
        )
        if type_filter is not None:
            notes_stmt = notes_stmt.where(Note.type == type_filter)

        note_rows = self.session.execute(notes_stmt).all()
        if not note_rows:
            return []

        top_ids = [row.id for row in note_rows]

        chunk_distance = Chunk.embedding.cosine_distance(query_embedding)
        chunks_stmt = (
            select(
                Chunk.note_fk,
                Chunk.section_header,
                Chunk.chunk_text,
            )
            .where(Chunk.note_fk.in_(top_ids))
            .order_by(Chunk.note_fk, chunk_distance)
            .distinct(Chunk.note_fk)
        )

        chunk_rows = self.session.execute(chunks_stmt).all()
        best_chunk_by_note = {
            row.note_fk: (row.section_header, row.chunk_text) for row in chunk_rows
        }

        results: list[dict] = []
        for row in note_rows:
            section, chunk_text = best_chunk_by_note.get(row.id, ("", ""))
            results.append(
                {
                    "note_id": row.note_id,
                    "title": row.title,
                    "path": row.path,
                    "type": row.type,
                    "tags": list(row.tags or []),
                    "score": float(row.score),
                    "section": section,
                    "snippet": (chunk_text or "")[:240],
                }
            )
        return results

    def get_note_by_id(self, note_id: str) -> dict | None:
        """Fetch lightweight note metadata by stable ``note_id``.

        Returns ``None`` if no note matches. Used by the knowledge search
        overlay's preview pane (ADR 003) to resolve a selected result to
        its displayable metadata without re-running the vector query.
        """
        row = self.session.execute(
            select(
                Note.note_id,
                Note.title,
                Note.path,
                Note.type,
                Note.tags,
            )
            .where(Note.note_id == note_id)
            .limit(1)
        ).first()
        if row is None:
            return None
        return {
            "note_id": row.note_id,
            "title": row.title,
            "path": row.path,
            "type": row.type,
            "tags": list(row.tags or []),
        }

    def delete_note(self, path: str) -> None:
        existing = self.session.execute(
            select(Note.id).where(Note.path == path)
        ).scalar_one_or_none()
        if existing is None:
            logger.info("knowledge: delete_note called for absent path %s", path)
            return
        self.session.execute(delete(Chunk).where(Chunk.note_fk == existing))
        self.session.execute(delete(NoteLink).where(NoteLink.src_note_fk == existing))
        self.session.execute(delete(Note).where(Note.id == existing))
        self.session.commit()
