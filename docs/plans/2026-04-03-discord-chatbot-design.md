# Discord Chatbot Design

**Date:** 2026-04-03
**Status:** Approved

## Overview

A conversational Discord chatbot integrated into the monolith, backed by Gemma 4 26B via llama.cpp, with persistent memory via pgvector and web search via SearXNG. Replaces the existing TypeScript chat bot in agent-platform.

## Goals

- Multi-turn conversational chatbot in Discord with persistent, unbounded history
- Semantic recall over past messages (channel-scoped, filterable by user)
- Web search capability via tool calling (Gemma decides when to search)
- Sandboxed — no MCP tools, no cluster access, no orchestrator integration
- Consolidate into the monolith, retire the TypeScript chat bot

## Non-Goals

- OpenWebUI-style UI — Discord is the only interface (for now)
- MCP tool access or cluster operations
- Migration of existing chat bot features (orchestrator job submission, NATS notifications) — these are being sunset

## Architecture

```
Discord Channel
    ↕ (WebSocket gateway)
Monolith (FastAPI + discord.py)
    ├── chat module
    │   ├── Discord listener (on_message)
    │   ├── Message storage (pgvector, chat schema)
    │   ├── Recall engine (recent window + semantic search)
    │   ├── PydanticAI agent (tool call loop)
    │   └── web_search tool (SearXNG)
    ├── todo module (existing)
    ├── notes module (existing)
    └── schedule module (existing)

External services:
    ├── Gemma 4 26B → llama-cpp (node-4) — /v1/chat/completions
    ├── voyage-4-nano → llama-cpp #2 (node-4) — /v1/embeddings
    ├── SearXNG → monolith namespace — /search?format=json
    └── PostgreSQL → monolith-pg (pgvector enabled)
```

### Message Flow

1. User sends message in Discord channel
2. discord.py receives it via gateway WebSocket
3. Store message + embedding in `chat.messages` (pgvector)
4. Build context: last N messages + semantic search for relevant older messages
5. PydanticAI agent runs with `web_search` tool available
6. If Gemma calls `web_search`, PydanticAI executes it (hits SearXNG), feeds results back
7. Gemma produces final response
8. Store bot response + embedding
9. Reply in Discord

## Data Model

Uses SQLModel + Atlas for schema management (same pattern as existing monolith modules).

```python
class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "chat"}

    id: int | None = Field(default=None, primary_key=True)
    discord_message_id: str = Field(unique=True)
    channel_id: str = Field(index=True)
    user_id: str
    username: str
    content: str
    is_bot: bool = Field(default=False)
    embedding: list[float] = Field(sa_column=Column(Vector(512)))
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Indexes

- HNSW index on `embedding` (vector_cosine_ops) for semantic search
- Composite index on `(channel_id, created_at DESC)` for recent window queries
- Composite index on `(channel_id, user_id, created_at DESC)` for per-user filtering

### Migration

- `CREATE EXTENSION pgvector` on monolith-pg
- `CREATE SCHEMA chat` + table + indexes
- Managed by Atlas operator via `AtlasMigration` CRD

## Context Assembly & Recall

On each incoming message:

1. **Recent window** — last 20 messages in the channel (by `created_at DESC`)
2. **Semantic search** — query pgvector with the incoming message's embedding, filtered by `channel_id`, excluding IDs already in the recent window. Top 5-10 results. Optionally filtered by `user_id`.
3. **Prompt assembly** — system prompt + semantically relevant older messages (with timestamps) + recent window + current message

## Tool Calling

PydanticAI manages the tool call loop with Gemma via llama.cpp's OpenAI-compatible API (jinja templating already enabled).

### Tools

- `web_search(query: str) -> str` — Queries SearXNG, returns top 5 results with title + content snippet

No other tools. The bot is intentionally sandboxed.

## Discord Integration

### Gateway

discord.py `Client` runs as a background task in the FastAPI lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = discord.Client(intents=...)
    asyncio.create_task(bot.start(token))
    yield
    await bot.close()
```

### Behavior

- Stores every message in configured channels (user and bot) with embeddings
- Only responds when mentioned (`@bot`) or replied to
- Shows typing indicator while generating
- Health check reflects Discord gateway status

### Intents

- `message_content` — read message text
- `guilds` — channel info
- Default intents for presence/member cache

### Secrets

Same 1Password item as the old chat bot (`vaults/k8s-homelab/items/discord-bot`):

- `DISCORD_BOT_TOKEN`

## New Infrastructure

### SearXNG

- Deployed as a Helm subchart dependency in the monolith chart
- Image: `searxng/searxng`
- Port: 8080
- Service: `monolith-searxng:8080`
- Resources: ~50-100Mi RAM
- Config: JSON API only, no web UI
- Stateless — no persistence needed

### voyage-4-nano (Embedding Model)

- Second llama.cpp instance on node-4 (GPU)
- Reuses the existing llama-cpp Helm chart with different values
- Model: voyage-4-nano GGUF via OCI image volume
- Endpoint: `/v1/embeddings`
- Resources: ~400MB VRAM, ~500MB RAM
- Service: `llama-cpp-embeddings.<namespace>.svc.cluster.local:8080`

### pgvector

- `CREATE EXTENSION pgvector` on existing monolith-pg
- No new Postgres deployment

## Retired Infrastructure

- `projects/agent_platform/chat_bot/` — TypeScript chat bot removed entirely
- No feature migration — orchestrator job submission and NATS notifications are sunset

## Dependencies

### Python Packages

- `discord.py` — Discord gateway client
- `pydantic-ai` — Agent framework with tool calling
- `pgvector` — SQLAlchemy/SQLModel pgvector integration
- `httpx` — Async HTTP client (for SearXNG + llama-cpp calls)

### Existing

- `sqlmodel` — ORM (already in monolith)
- `fastapi` — HTTP framework (already in monolith)
- `psycopg` — Postgres driver (already in monolith)

## Environment Variables

| Variable            | Source      | Purpose                           |
| ------------------- | ----------- | --------------------------------- |
| `DISCORD_BOT_TOKEN` | 1Password   | Discord gateway auth              |
| `DATABASE_URL`      | CNPG secret | Postgres connection (existing)    |
| `LLAMA_CPP_URL`     | Helm values | Gemma completions endpoint        |
| `EMBEDDING_URL`     | Helm values | voyage-4-nano embeddings endpoint |
| `SEARXNG_URL`       | Helm values | SearXNG search endpoint           |
