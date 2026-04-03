"""Message store -- persist and recall chat messages with pgvector."""

import logging

from sqlmodel import Session, select

from chat.embedding import EmbeddingClient
from chat.models import Message

logger = logging.getLogger(__name__)


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
    ) -> Message:
        """Embed and persist a message."""
        embedding = await self.embed_client.embed(content)
        msg = Message(
            discord_message_id=discord_message_id,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            content=content,
            is_bot=is_bot,
            embedding=embedding,
        )
        self.session.add(msg)
        self.session.commit()
        self.session.refresh(msg)
        return msg

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
        params = {
            "channel_id": channel_id,
            "embedding": str(query_embedding),
            "limit": limit,
        }

        filters = "channel_id = :channel_id"
        if exclude:
            filters += " AND id NOT IN (" + ",".join(str(i) for i in exclude) + ")"
        if user_id:
            filters += " AND user_id = :user_id"
            params["user_id"] = user_id

        sql = text(
            f"SELECT * FROM chat.messages WHERE {filters} "
            "ORDER BY embedding <=> :embedding LIMIT :limit"
        )
        result = self.session.exec(sql, params=params)
        return [Message.model_validate(row) for row in result]
