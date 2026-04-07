"""Rolling summary generator -- incrementally updates per-user-per-channel summaries."""

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from chat.models import ChannelSummary, Message, UserChannelSummary

logger = logging.getLogger(__name__)


async def generate_summaries(
    session: Session,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Update rolling summaries for all (channel, user) pairs with new messages."""
    pairs = session.exec(
        select(Message.channel_id, Message.user_id, Message.username)
        .where(Message.is_bot == False)  # noqa: E712
        .group_by(Message.channel_id, Message.user_id, Message.username)
    ).all()

    for channel_id, user_id, username in pairs:
        try:
            existing = session.exec(
                select(UserChannelSummary).where(
                    UserChannelSummary.channel_id == channel_id,
                    UserChannelSummary.user_id == user_id,
                )
            ).first()

            high_water = existing.last_message_id if existing else 0

            new_messages = list(
                session.exec(
                    select(Message)
                    .where(
                        Message.channel_id == channel_id,
                        Message.user_id == user_id,
                        Message.is_bot == False,  # noqa: E712
                        Message.id > high_water,
                    )
                    .order_by(Message.created_at.asc())
                ).all()
            )

            if not new_messages:
                continue

            new_max_id = max(m.id for m in new_messages)
            messages_text = "\n".join(
                f"[{m.created_at.strftime('%Y-%m-%d %H:%M')}] {m.content}"
                for m in new_messages
            )

            if existing:
                prompt = (
                    f"Current summary of {username}'s messages:\n{existing.summary}\n\n"
                    f"New messages from {username}:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on patterns, topics, and context from OLDER messages "
                    "that would help the bot understand this person better. "
                    "Keep it to 2-4 concise sentences."
                )
            else:
                prompt = (
                    f"Messages from {username}:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on patterns, topics, and context from OLDER messages "
                    "that would help the bot understand this person better. "
                    "Write a 2-4 sentence summary of this user's key topics, interests, "
                    "and communication style."
                )

            summary_text = await llm_call(prompt)

            if existing:
                existing.summary = summary_text
                existing.username = username
                existing.last_message_id = new_max_id
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
            else:
                session.add(
                    UserChannelSummary(
                        channel_id=channel_id,
                        user_id=user_id,
                        username=username,
                        summary=summary_text,
                        last_message_id=new_max_id,
                    )
                )
            session.commit()
        except Exception:
            logger.exception(
                "Failed to generate summary for %s/%s", channel_id, username
            )
            continue

    logger.info("Summary generation complete for %d user-channel pairs", len(pairs))


async def generate_channel_summaries(
    session: Session,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Update rolling summaries for all channels with new messages."""
    channels = session.exec(
        select(Message.channel_id).group_by(Message.channel_id)
    ).all()

    for (channel_id,) in [(c,) if isinstance(c, str) else c for c in channels]:
        try:
            existing = session.exec(
                select(ChannelSummary).where(
                    ChannelSummary.channel_id == channel_id,
                )
            ).first()

            high_water = existing.last_message_id if existing else 0

            new_messages = list(
                session.exec(
                    select(Message)
                    .where(
                        Message.channel_id == channel_id,
                        Message.id > high_water,
                    )
                    .order_by(Message.created_at.asc())
                ).all()
            )

            if not new_messages:
                continue

            new_max_id = max(m.id for m in new_messages)
            total_count = (existing.message_count if existing else 0) + len(
                new_messages
            )
            messages_text = "\n".join(
                f"[{m.created_at.strftime('%Y-%m-%d %H:%M')}] {m.username}: {m.content}"
                for m in new_messages
            )

            if existing:
                prompt = (
                    f"Current channel summary:\n{existing.summary}\n\n"
                    f"New messages:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on the channel's overall topics, culture, and "
                    "recurring themes from OLDER messages. "
                    "Keep it to 2-4 concise sentences."
                )
            else:
                prompt = (
                    f"Messages from a Discord channel:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on the channel's overall topics, culture, and "
                    "recurring themes from OLDER messages. "
                    "Write a 2-4 sentence summary of what this channel is about."
                )

            summary_text = await llm_call(prompt)

            if existing:
                existing.summary = summary_text
                existing.last_message_id = new_max_id
                existing.message_count = total_count
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
            else:
                session.add(
                    ChannelSummary(
                        channel_id=channel_id,
                        summary=summary_text,
                        last_message_id=new_max_id,
                        message_count=total_count,
                    )
                )
            session.commit()
        except Exception:
            logger.exception("Failed to generate channel summary for %s", channel_id)
            continue

    logger.info("Channel summary generation complete for %d channels", len(channels))


def on_startup(
    session: "Session",
    *,
    bot: "discord.Client | None" = None,
    llm_call: Callable[[str], Awaitable[str]] | None = None,
) -> None:
    """Register chat jobs with the scheduler."""
    from shared.scheduler import register_job

    if llm_call is None:
        llm_call = build_llm_caller()

    async def _summary_handler(session: "Session") -> None:
        await generate_summaries(session, llm_call)
        await generate_channel_summaries(session, llm_call)
        return None

    register_job(
        session,
        name="chat.summary_generation",
        interval_secs=86400,
        handler=_summary_handler,
        ttl_secs=1800,
    )

    if bot is not None:
        from chat.changelog import run_changelog_iteration

        async def _changelog_handler(session: "Session") -> None:
            await run_changelog_iteration(bot, llm_call)
            return None

        register_job(
            session,
            name="chat.changelog",
            interval_secs=3600,
            handler=_changelog_handler,
            ttl_secs=300,
        )


def build_llm_caller(base_url: str | None = None) -> Callable[[str], Awaitable[str]]:
    """Create an async callable that sends a prompt to Gemma via llama.cpp."""
    url = base_url or os.environ.get("LLAMA_CPP_URL", "")
    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def call_llm(prompt: str) -> str:
        resp = await client.post(
            f"{url}/v1/chat/completions",
            json={
                "model": "gemma-4-26b-a4b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16384,
            },
        )
        resp.raise_for_status()
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise RuntimeError(f"unexpected LLM response shape: {e}") from e

    return call_llm
