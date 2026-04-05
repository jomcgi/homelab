"""Message store -- persist and recall chat messages with pgvector."""

import hashlib
import logging

from sqlmodel import Session, select

from chat.embedding import EmbeddingClient
from chat.models import Attachment, Blob, Message, UserChannelSummary

logger = logging.getLogger(__name__)


def _build_embed_text(content: str, descriptions: list[str]) -> str:
    """Combine message text with image descriptions for embedding."""
    if not descriptions:
        return content
    image_parts = "\n".join(f"[Image: {d}]" for d in descriptions)
    return f"{content}\n\n{image_parts}"


class MessageStore:
    def __init__(self, session: Session, embed_client: EmbeddingClient):
        self.session = session
        self.embed_client = embed_client

    async def save_message(
        self,
        discord_message_id: str,
        channel_id: str,
        user_id: str,
        username: str,
        content: str,
        is_bot: bool,
        attachments: list[dict] | None = None,
    ) -> Message | None:
        """Embed and persist a message. Returns None if already stored."""
        from sqlalchemy.exc import IntegrityError

        descriptions = [
            a["description"] for a in (attachments or []) if a.get("description")
        ]
        embed_text = _build_embed_text(content, descriptions)
        embedding = await self.embed_client.embed(embed_text)
        msg = Message(
            discord_message_id=discord_message_id,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            content=content,
            is_bot=is_bot,
            embedding=embedding,
        )
        try:
            self.session.add(msg)
            self.session.flush()
            if attachments:
                for a in attachments:
                    sha = hashlib.sha256(a["data"]).hexdigest()
                    existing_blob = self.session.get(Blob, sha)
                    if not existing_blob:
                        self.session.add(
                            Blob(
                                sha256=sha,
                                data=a["data"],
                                content_type=a["content_type"],
                                description=a.get("description", ""),
                            )
                        )
                    self.session.add(
                        Attachment(
                            message_id=msg.id,
                            blob_sha256=sha,
                            filename=a["filename"],
                        )
                    )
            self.session.commit()
            self.session.refresh(msg)
            return msg
        except IntegrityError:
            self.session.rollback()
            return None

    def get_recent(self, channel_id: str, limit: int = 20) -> list[Message]:
        """Return the most recent messages in a channel, oldest first."""
        stmt = (
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(self.session.exec(stmt).all())
        messages.reverse()
        return messages

    def search_similar(
        self,
        channel_id: str,
        query_embedding: list[float],
        limit: int = 5,
        exclude_ids: list[int] | None = None,
        user_id: str | None = None,
    ) -> list[Message]:
        """Semantic search over channel history using pgvector cosine distance.

        Note: This uses raw SQL because SQLModel doesn't natively support
        pgvector's <=> operator. Falls back gracefully in SQLite tests.
        """
        from sqlalchemy import text

        exclude = exclude_ids or []
        params: dict[str, object] = {
            "channel_id": channel_id,
            "embedding": str(query_embedding),
            "limit": limit,
        }

        # Raw SQL is required here because pgvector's <=> cosine distance
        # operator has no SQLModel/SQLAlchemy ORM equivalent.
        filters = "channel_id = :channel_id"
        if exclude:
            # Bind each excluded ID as a separate parameter to avoid
            # string interpolation in the SQL statement.
            placeholders = []
            for idx, eid in enumerate(exclude):
                key = f"excl_{idx}"
                placeholders.append(f":{key}")
                params[key] = int(eid)
            filters += f" AND id NOT IN ({', '.join(placeholders)})"
        if user_id:
            filters += " AND user_id = :user_id"
            params["user_id"] = user_id

        sql = text(
            f"SELECT * FROM chat.messages WHERE {filters} "
            "ORDER BY embedding <=> :embedding LIMIT :limit"
        )
        result = self.session.exec(sql, params=params)
        return [Message.model_validate(row) for row in result]

    def get_attachments(
        self, message_ids: list[int]
    ) -> dict[int, list[tuple[Attachment, Blob]]]:
        """Load attachments with their blobs for a set of message IDs."""
        if not message_ids:
            return {}
        stmt = (
            select(Attachment, Blob)
            .join(Blob, Attachment.blob_sha256 == Blob.sha256)
            .where(Attachment.message_id.in_(message_ids))
        )
        result: dict[int, list[tuple[Attachment, Blob]]] = {}
        for att, blob in self.session.exec(stmt).all():
            result.setdefault(att.message_id, []).append((att, blob))
        return result

    def get_blob(self, sha256: str) -> Blob | None:
        """Look up a blob by its content hash."""
        return self.session.get(Blob, sha256)

    def find_user_id_by_username(self, channel_id: str, username: str) -> str | None:
        """Look up a user_id by username within a channel. Returns None if not found."""
        stmt = (
            select(Message.user_id)
            .where(Message.channel_id == channel_id, Message.username == username)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return self.session.exec(stmt).first()

    def list_user_summaries(self, channel_id: str) -> list[UserChannelSummary]:
        """Return all user summaries for a channel, ordered by most recently updated."""
        stmt = (
            select(UserChannelSummary)
            .where(UserChannelSummary.channel_id == channel_id)
            .order_by(UserChannelSummary.updated_at.desc())
        )
        return list(self.session.exec(stmt).all())

    def get_user_summary(
        self, channel_id: str, username: str
    ) -> UserChannelSummary | None:
        """Return the rolling summary for a user in a channel, or None."""
        stmt = select(UserChannelSummary).where(
            UserChannelSummary.channel_id == channel_id,
            UserChannelSummary.username == username,
        )
        return self.session.exec(stmt).first()

    def upsert_summary(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        summary_text: str,
        last_message_id: int,
    ) -> None:
        """Insert or update a rolling summary for a user in a channel."""
        from datetime import datetime, timezone

        existing = self.session.exec(
            select(UserChannelSummary).where(
                UserChannelSummary.channel_id == channel_id,
                UserChannelSummary.user_id == user_id,
            )
        ).first()
        if existing:
            existing.summary = summary_text
            existing.username = username
            existing.last_message_id = last_message_id
            existing.updated_at = datetime.now(timezone.utc)
            self.session.add(existing)
        else:
            self.session.add(
                UserChannelSummary(
                    channel_id=channel_id,
                    user_id=user_id,
                    username=username,
                    summary=summary_text,
                    last_message_id=last_message_id,
                )
            )
        self.session.commit()
