"""Postgres data access layer for the knowledge schema."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

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
                self.session.execute(delete(Chunk).where(Chunk.note_id == existing))
                self.session.execute(
                    delete(NoteLink).where(NoteLink.src_note_id == existing)
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
                        note_id=note.id,
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
                        src_note_id=note.id,
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
                            src_note_id=note.id,
                            target_id=target,
                            target_title=None,
                            kind="edge",
                            edge_type=edge_type,
                        )
                    )
            self.session.flush()

        self.session.commit()

    def delete_note(self, path: str) -> None:
        existing = self.session.execute(
            select(Note.id).where(Note.path == path)
        ).scalar_one_or_none()
        if existing is None:
            logger.info("knowledge: delete_note called for absent path %s", path)
            return
        self.session.execute(delete(Chunk).where(Chunk.note_id == existing))
        self.session.execute(delete(NoteLink).where(NoteLink.src_note_id == existing))
        self.session.execute(delete(Note).where(Note.id == existing))
        self.session.commit()
