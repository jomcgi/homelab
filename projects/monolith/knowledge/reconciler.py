"""Vault → knowledge schema reconciler."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from pathlib import Path
from typing import Protocol

from sqlalchemy import text

from knowledge import frontmatter, links
from knowledge.frontmatter import FrontmatterError
from knowledge.store import KnowledgeStore
from shared.chunker import chunk_markdown

logger = logging.getLogger("monolith.knowledge.reconciler")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ReadOnlyVaultError(Exception):
    """Raised when the vault is read-only and a file lacks a frontmatter id.

    We refuse to ingest with an ephemeral id because the id would not be
    stable across restarts — graph edges pointing at the ephemeral id
    would silently break.
    """


class _Embedder(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class Reconciler:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        embed_client: _Embedder,
        vault_root: Path,
    ) -> None:
        self.store = store
        self.embed_client = embed_client
        self.vault_root = Path(vault_root)
        self.processed_root = self.vault_root / "_processed"

    async def run(self) -> tuple[int, int, int]:
        """Returns (upserted, deleted, unchanged)."""
        indexed = self.store.get_indexed()
        on_disk = self._walk(previous_indexed=indexed)

        to_upsert = sorted(
            path for path, h in on_disk.items() if indexed.get(path) != h
        )
        to_delete = sorted(path for path in indexed if path not in on_disk)
        unchanged = len(on_disk) - len(to_upsert)

        first_error: BaseException | None = None
        for path in to_delete:
            logger.info("knowledge: deleting %s", path)
            try:
                self.store.delete_note(path)
            except Exception as exc:  # noqa: BLE001 — partial-failure isolation
                logger.exception("knowledge: failed to delete %s, continuing", path)
                if first_error is None:
                    first_error = exc
                try:
                    self.store.session.rollback()
                except Exception:  # noqa: BLE001
                    logger.exception("knowledge: rollback after delete failure failed")
                continue

        upserted = 0
        for path in to_upsert:
            try:
                ingested = await self._ingest_one(path, on_disk[path])
            except FileNotFoundError:
                logger.warning("knowledge: file vanished mid-cycle: %s", path)
                continue
            except FrontmatterError as exc:
                # A broken frontmatter block must NOT overwrite the
                # existing row with empty defaults — skip the file and
                # leave the prior index entry intact.
                logger.warning(
                    "knowledge: skipping note with invalid frontmatter %s: %s",
                    path,
                    exc,
                )
                try:
                    self.store.session.rollback()
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "knowledge: rollback after frontmatter error failed"
                    )
                continue
            except Exception as exc:  # noqa: BLE001 — partial-failure isolation
                logger.exception("knowledge: failed to ingest %s, continuing", path)
                if first_error is None:
                    first_error = exc
                # Roll back any uncommitted state from the failed ingest so
                # the next file starts with a clean session.
                try:
                    self.store.session.rollback()
                except Exception:  # noqa: BLE001
                    logger.exception("knowledge: rollback after failure failed")
                continue
            if ingested:
                upserted += 1

        logger.info(
            "knowledge: reconciled upserted=%d deleted=%d unchanged=%d",
            upserted,
            len(to_delete),
            unchanged,
        )
        if first_error is not None:
            raise first_error
        return upserted, len(to_delete), unchanged

    def _walk(self, *, previous_indexed: dict[str, str]) -> dict[str, str]:
        if not self.processed_root.exists():
            return {}
        out: dict[str, str] = {}
        for p in self.processed_root.rglob("*.md"):
            rel = p.relative_to(self.vault_root).as_posix()
            try:
                data = p.read_bytes()
            except FileNotFoundError:
                # Genuine race with unlink — let the delete loop handle it
                # on the next cycle (or this cycle, if get_indexed still
                # lists it).
                continue
            except (PermissionError, OSError):
                # Transient read error: carry forward the previous hash so
                # the file stays in the snapshot under its old hash and is
                # neither marked for delete nor for re-ingestion.
                logger.warning("knowledge: skipping unreadable file %s", rel)
                if rel in previous_indexed:
                    out[rel] = previous_indexed[rel]
                continue
            out[rel] = hashlib.sha256(data).hexdigest()
        return out

    def _read_text(self, abs_path: Path) -> str:
        try:
            return abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("knowledge: invalid utf-8, skipping: %s", abs_path)
            raise

    async def _ingest_one(self, rel_path: str, content_hash: str) -> bool:
        # Per-file advisory lock prevents producer/consumer races (gardener
        # writing the same file mid-cycle, or two replicas if locking ever
        # weakens). Lock is auto-released at txn end. Postgres-only — the
        # SQLite test fixture skips this branch.
        session = self.store.session
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            locked = session.execute(
                text("SELECT pg_try_advisory_xact_lock(hashtext(:p))"),
                {"p": rel_path},
            ).scalar()
            if not locked:
                logger.info("knowledge: advisory lock busy, deferring %s", rel_path)
                return False

        abs_path = self.vault_root / rel_path
        try:
            raw = self._read_text(abs_path)
        except UnicodeDecodeError:
            return False

        meta, body = frontmatter.parse(raw)
        title = meta.title or Path(rel_path).stem

        # Auto-backfill missing note_id. Mandatory: every row must have one.
        note_id = meta.note_id
        if not note_id:
            note_id = _slugify(title)
            try:
                raw, content_hash = self._write_back_id(abs_path, raw, note_id)
                meta, body = frontmatter.parse(raw)
            except PermissionError as exc:
                raise ReadOnlyVaultError(
                    f"vault is read-only and {rel_path} has no frontmatter id;"
                    " refusing to ingest with ephemeral id"
                ) from exc

        chunks = chunk_markdown(body)
        if not chunks:
            chunks = [{"index": 0, "section_header": "", "text": body or title}]
        vectors = await self.embed_client.embed_batch([c["text"] for c in chunks])
        wikilinks = links.extract(body)

        self.store.upsert_note(
            note_id=note_id,
            path=rel_path,
            content_hash=content_hash,
            title=title,
            metadata=meta,
            chunks=chunks,
            vectors=vectors,
            links=wikilinks,
        )
        return True

    def _write_back_id(self, abs_path: Path, raw: str, note_id: str) -> tuple[str, str]:
        """Inject ``id: <note_id>`` into the file's frontmatter.

        Returns the new ``(raw, content_hash)``. Raises ``PermissionError``
        on read-only mounts.
        """
        if raw.startswith("---\n"):
            new_raw = f"---\nid: {note_id}\n" + raw[len("---\n") :]
        else:
            new_raw = f"---\nid: {note_id}\n---\n{raw}"
        abs_path.write_text(new_raw, encoding="utf-8")
        new_hash = hashlib.sha256(new_raw.encode("utf-8")).hexdigest()
        return new_raw, new_hash


def _slugify(text_in: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_in)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug or "note"
