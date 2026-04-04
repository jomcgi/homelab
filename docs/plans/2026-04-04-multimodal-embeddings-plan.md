# Multi-Modal Discord Message Embeddings — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the Discord bot to store image attachments, describe them with Gemma 4 vision, and embed the descriptions with voyage-4-nano for semantic search.

**Architecture:** New `chat.attachments` table stores raw image bytes + Gemma descriptions linked to messages via FK. `VisionClient` calls Gemma 4's OpenAI-compatible vision endpoint. Embeddings combine text + image descriptions. Response generation re-sends stored images to Gemma for full visual context.

**Tech Stack:** PostgreSQL/pgvector (BYTEA), llama.cpp (Gemma 4 vision + voyage-4-nano), discord.py, SQLModel, httpx, PydanticAI

---

### Task 1: Attachment Model

**Files:**

- Modify: `projects/monolith/chat/models.py`
- Test: `projects/monolith/chat/models_test.py`

**Step 1: Write the failing tests**

Add to `models_test.py`:

```python
from chat.models import Attachment, Message


class TestAttachmentModel:
    def test_attachment_table_name(self):
        """Attachment model maps to chat.attachments table."""
        assert Attachment.__tablename__ == "attachments"
        assert Attachment.__table_args__["schema"] == "chat"

    def test_attachment_has_required_fields(self):
        """Attachment model has all expected columns."""
        columns = {c.name for c in Attachment.__table__.columns}
        expected = {"id", "message_id", "data", "content_type", "filename", "description"}
        assert expected == columns

    def test_attachment_construction(self):
        """Attachment can be constructed with all fields."""
        att = Attachment(
            message_id=1,
            data=b"\x89PNG",
            content_type="image/png",
            filename="photo.png",
            description="A photo of a cat",
        )
        assert att.content_type == "image/png"
        assert att.data == b"\x89PNG"
```

**Step 2: Run tests to verify they fail**

Push and let CI run. Expected: `ImportError: cannot import name 'Attachment' from 'chat.models'`

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/models.py`:

```python
class Attachment(SQLModel, table=True):
    __tablename__ = "attachments"
    __table_args__ = {"schema": "chat"}

    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="chat.messages.id")
    data: bytes
    content_type: str
    filename: str
    description: str
```

**Step 4: Run tests to verify they pass**

Push and let CI run. Expected: all `TestAttachmentModel` tests PASS.

**Step 5: Commit**

```
feat(monolith): add Attachment model for image storage
```

---

### Task 2: Database Migration

**Files:**

- Create: `projects/monolith/chart/migrations/20260404000000_chat_attachments.sql`

**Step 1: Write migration**

```sql
CREATE TABLE chat.attachments (
    id SERIAL PRIMARY KEY,
    message_id INT NOT NULL REFERENCES chat.messages(id) ON DELETE CASCADE,
    data BYTEA NOT NULL,
    content_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE INDEX chat_attachments_message_id ON chat.attachments (message_id);
```

**Step 2: Verify migration renders in Helm**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml --show-only templates/cnpg-cluster.yaml
```

Verify the migration file appears in the ConfigMap or is picked up by the CNPG init mechanism.

**Step 3: Commit**

```
feat(monolith): add chat.attachments migration for image storage
```

---

### Task 3: VisionClient

**Files:**

- Create: `projects/monolith/chat/vision.py`
- Create: `projects/monolith/chat/vision_test.py`

**Step 1: Write the failing test**

Create `projects/monolith/chat/vision_test.py`:

```python
"""Tests for the vision client (calls Gemma 4 via llama.cpp)."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.vision import VisionClient


@pytest.fixture
def client():
    return VisionClient(base_url="http://fake:8080")


class TestVisionClient:
    @pytest.mark.asyncio
    async def test_describe_returns_text(self, client):
        """describe() returns a text description from Gemma 4 vision."""
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "A photo of a sunset over the ocean"}}]
        }

        with patch("chat.vision.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            result = await client.describe(b"\x89PNG\r\n", "image/png")

        assert result == "A photo of a sunset over the ocean"

    @pytest.mark.asyncio
    async def test_describe_sends_base64_image(self, client):
        """describe() sends the image as base64 in the vision content array."""
        image_bytes = b"\x89PNG\r\n"
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "A picture"}}]
        }

        with patch("chat.vision.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            await client.describe(image_bytes, "image/png")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        messages = payload["messages"]
        user_msg = messages[-1]
        assert isinstance(user_msg["content"], list)
        image_part = [p for p in user_msg["content"] if p["type"] == "image_url"][0]
        expected_b64 = base64.b64encode(image_bytes).decode()
        assert f"data:image/png;base64,{expected_b64}" in image_part["image_url"]["url"]
```

**Step 2: Run tests to verify they fail**

Push and let CI run. Expected: `ModuleNotFoundError: No module named 'chat.vision'`

**Step 3: Write minimal implementation**

Create `projects/monolith/chat/vision.py`:

```python
"""Vision client -- calls Gemma 4 via llama.cpp /v1/chat/completions for image description."""

import base64
import os

import httpx

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")

VISION_SYSTEM_PROMPT = (
    "Describe this image concisely for semantic search. "
    "Focus on the key subjects, actions, and notable details."
)


class VisionClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or LLAMA_CPP_URL

    async def describe(self, image_bytes: bytes, content_type: str) -> str:
        """Describe an image using Gemma 4 vision, returning a text summary."""
        b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:{content_type};base64,{b64}"

        payload = {
            "model": "gemma-4-26b-a4b",
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image."},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "max_tokens": 256,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
```

**Step 4: Run tests to verify they pass**

Push and let CI run. Expected: all `TestVisionClient` tests PASS.

**Step 5: Commit**

```
feat(monolith): add VisionClient for Gemma 4 image description
```

---

### Task 4: Update MessageStore to Handle Attachments

**Files:**

- Modify: `projects/monolith/chat/store.py`
- Modify: `projects/monolith/chat/store_test.py`

**Step 1: Write the failing tests**

Add to `store_test.py` (update import to include `Attachment`):

```python
from chat.models import Attachment, Message


class TestSaveMessageWithAttachments:
    @pytest.mark.asyncio
    async def test_saves_attachments_linked_to_message(self, store, session):
        """save_message persists attachments linked to the message."""
        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "photo.png",
                "description": "A cat",
            }
        ]
        msg = await store.save_message(
            discord_message_id="att1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Look at this!",
            is_bot=False,
            attachments=attachments,
        )
        assert msg is not None
        saved = session.exec(select(Attachment)).all()
        assert len(saved) == 1
        assert saved[0].message_id == msg.id
        assert saved[0].description == "A cat"
        assert saved[0].data == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_embeds_combined_text_and_descriptions(self, store):
        """save_message embeds text content combined with image descriptions."""
        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "photo.png",
                "description": "A sunset",
            },
            {
                "data": b"\xff\xd8\xff",
                "content_type": "image/jpeg",
                "filename": "sky.jpg",
                "description": "Blue sky with clouds",
            },
        ]
        await store.save_message(
            discord_message_id="att2",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Beautiful day!",
            is_bot=False,
            attachments=attachments,
        )
        embed_call = store.embed_client.embed.call_args[0][0]
        assert "Beautiful day!" in embed_call
        assert "[Image: A sunset]" in embed_call
        assert "[Image: Blue sky with clouds]" in embed_call

    @pytest.mark.asyncio
    async def test_text_only_message_unchanged(self, store):
        """save_message without attachments behaves as before."""
        await store.save_message(
            discord_message_id="noatt",
            channel_id="ch1",
            user_id="u1",
            username="Carol",
            content="Just text",
            is_bot=False,
        )
        store.embed_client.embed.assert_called_once_with("Just text")


class TestGetAttachments:
    @pytest.mark.asyncio
    async def test_get_attachments_for_messages(self, store, session):
        """get_attachments returns attachments keyed by message id."""
        msg = await store.save_message(
            discord_message_id="ga1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Photo",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "a.png",
                    "description": "Cat",
                },
            ],
        )
        result = store.get_attachments([msg.id])
        assert msg.id in result
        assert len(result[msg.id]) == 1
        assert result[msg.id][0].filename == "a.png"
```

**Step 2: Run tests to verify they fail**

Push and let CI run. Expected: `TypeError: save_message() got an unexpected keyword argument 'attachments'`

**Step 3: Write minimal implementation**

Replace `projects/monolith/chat/store.py` with the updated version that:

- Adds `_build_embed_text()` helper to combine content + descriptions
- Adds optional `attachments` parameter to `save_message()`
- Uses `session.flush()` to get `msg.id` before inserting attachments
- Adds `get_attachments()` method
- Keeps `search_similar()` unchanged

Key changes to `save_message`:

```python
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
    descriptions = [a["description"] for a in (attachments or []) if a.get("description")]
    embed_text = _build_embed_text(content, descriptions)
    embedding = await self.embed_client.embed(embed_text)
    # ... create Message, flush, create Attachments, commit
```

New helper:

```python
def _build_embed_text(content: str, descriptions: list[str]) -> str:
    if not descriptions:
        return content
    image_parts = "\n".join(f"[Image: {d}]" for d in descriptions)
    return f"{content}\n\n{image_parts}"
```

New method:

```python
def get_attachments(self, message_ids: list[int]) -> dict[int, list[Attachment]]:
    if not message_ids:
        return {}
    stmt = select(Attachment).where(Attachment.message_id.in_(message_ids))
    result: dict[int, list[Attachment]] = {}
    for att in self.session.exec(stmt).all():
        result.setdefault(att.message_id, []).append(att)
    return result
```

**Step 4: Run tests to verify they pass**

Push and let CI run. Expected: all store tests PASS (old + new).

**Step 5: Commit**

```
feat(monolith): support image attachments in MessageStore
```

---

### Task 5: Update Bot to Process Image Attachments

**Files:**

- Modify: `projects/monolith/chat/bot.py`
- Modify: `projects/monolith/chat/bot_test.py`

**Step 1: Write the failing test**

Add to `bot_test.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from chat.bot import download_image_attachments


class TestDownloadImageAttachments:
    @pytest.mark.asyncio
    async def test_downloads_image_attachments(self):
        """download_image_attachments downloads images and describes them."""
        att = MagicMock()
        att.content_type = "image/png"
        att.filename = "photo.png"
        att.read = AsyncMock(return_value=b"\x89PNG")

        vision_client = AsyncMock()
        vision_client.describe.return_value = "A cat sitting on a chair"

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 1
        assert result[0]["data"] == b"\x89PNG"
        assert result[0]["content_type"] == "image/png"
        assert result[0]["filename"] == "photo.png"
        assert result[0]["description"] == "A cat sitting on a chair"

    @pytest.mark.asyncio
    async def test_skips_non_image_attachments(self):
        """download_image_attachments ignores non-image content types."""
        att = MagicMock()
        att.content_type = "application/pdf"
        att.filename = "doc.pdf"

        vision_client = AsyncMock()

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 0
        vision_client.describe.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_attachment_with_no_content_type(self):
        """download_image_attachments skips attachments without content_type."""
        att = MagicMock()
        att.content_type = None
        att.filename = "unknown"

        vision_client = AsyncMock()

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 0
```

**Step 2: Run tests to verify they fail**

Push and let CI run. Expected: `ImportError: cannot import name 'download_image_attachments'`

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/bot.py`:

- Import `VisionClient` from `chat.vision`
- Add `download_image_attachments()` async function that filters for `image/*`, downloads bytes via `att.read()`, calls `vision_client.describe()`
- Add `self.vision_client = VisionClient()` to `ChatBot.__init__`
- In `on_message`: call `download_image_attachments()`, pass result to `store.save_message(attachments=...)`
- In `_generate_response`: load attachments for recalled messages via `store.get_attachments()`, pass to `format_context_messages()`

**Step 4: Run tests to verify they pass**

Push and let CI run. Expected: all bot tests PASS.

**Step 5: Commit**

```
feat(monolith): process image attachments in Discord bot
```

---

### Task 6: Update Context Formatting with Image Descriptions

**Files:**

- Modify: `projects/monolith/chat/agent.py`
- Modify: `projects/monolith/chat/agent_test.py`

**Step 1: Write the failing test**

Add to `agent_test.py`:

```python
from datetime import datetime, timezone

from chat.agent import format_context_messages
from chat.models import Attachment, Message


class TestFormatContextMessages:
    def test_format_with_image_descriptions(self):
        """format_context_messages includes image descriptions when attachments present."""
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Check this out",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
        )
        attachments_map = {
            1: [
                Attachment(
                    id=1,
                    message_id=1,
                    data=b"",
                    content_type="image/png",
                    filename="cat.png",
                    description="A cat on a keyboard",
                ),
            ]
        }
        result = format_context_messages([msg], attachments_map)
        assert "Alice: Check this out" in result
        assert "[Image: A cat on a keyboard]" in result

    def test_format_without_attachments(self):
        """format_context_messages works with empty attachments map."""
        msg = Message(
            id=2,
            discord_message_id="2",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Just text",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
        )
        result = format_context_messages([msg])
        assert "Bob: Just text" in result
        assert "[Image:" not in result
```

**Step 2: Run tests to verify they fail**

Push and let CI run. Expected: signature mismatch on `format_context_messages`.

**Step 3: Write minimal implementation**

Update `format_context_messages` in `projects/monolith/chat/agent.py` to accept optional `attachments_by_msg` dict:

```python
def format_context_messages(
    messages: list[Message],
    attachments_by_msg: dict[int, list[Attachment]] | None = None,
) -> str:
    att_map = attachments_by_msg or {}
    lines = []
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        if msg.is_bot:
            lines.append(f"[{timestamp}] Assistant: {msg.content}")
        else:
            lines.append(f"[{timestamp}] {msg.username}: {msg.content}")
        for att in att_map.get(msg.id, []):
            lines.append(f"  [Image: {att.description}]")
    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Push and let CI run. Expected: all agent tests PASS.

**Step 5: Commit**

```
feat(monolith): include image descriptions in context formatting
```

---

### Task 7: Bump Chart Version

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml`
- Modify: `projects/monolith/deploy/application.yaml`

**Step 1: Check current versions**

Read both files to find current `version` and `targetRevision`.

**Step 2: Bump patch version**

Increment the patch version in both files. They MUST match.

**Step 3: Commit**

```
chore(monolith): bump chart version for multi-modal embeddings
```

---

### Task 8: Final Integration Verification

**Step 1: Run format**

```bash
format
```

Ensure all files pass formatting and BUILD files are up to date.

**Step 2: Render Helm templates**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml
```

Verify the migration ConfigMap includes the new attachments migration.

**Step 3: Push and verify CI**

Push all commits and verify CI passes.

**Step 4: Create PR**

```bash
gh pr create --title "feat(monolith): multi-modal image embeddings for Discord bot" --body "..."
```
