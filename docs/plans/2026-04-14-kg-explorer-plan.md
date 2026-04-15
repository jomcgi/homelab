# Knowledge Graph Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a chat-driven knowledge graph explorer at `private/chat` where Gemma-4 searches the KG via tools and a rough.js graph animates in real-time via SSE.

**Architecture:** PydanticAI agent with 3 tools (search_kg, expand_node, discard_node) streaming SSE events through a FastAPI endpoint, proxied by a SvelteKit `+server.js` to a Svelte 5 page that renders an incremental rough.js graph with smooth dagre re-layout transitions.

**Tech Stack:** PydanticAI, FastAPI StreamingResponse, SvelteKit, rough.js, dagre, marked (new dep)

**Design doc:** `docs/plans/2026-04-14-kg-explorer-design.md`

---

### Task 1: Add marked dependency for markdown rendering

**Files:**

- Modify: `projects/monolith/frontend/package.json`

**Step 1: Add marked**

```bash
cd projects/monolith/frontend && pnpm add marked
```

**Step 2: Verify install**

```bash
pnpm ls marked
```

Expected: `marked` version listed.

**Step 3: Commit**

```bash
git add projects/monolith/frontend/package.json projects/monolith/frontend/pnpm-lock.yaml
git commit -m "build(monolith): add marked for runtime markdown rendering"
```

---

### Task 2: Backend — SSE emitter utility

**Files:**

- Create: `projects/monolith/chat/sse.py`
- Create: `projects/monolith/chat/sse_test.py`

The SSE emitter is a thin wrapper that formats events as `data: {json}\n\n` and pushes them onto an asyncio queue. The agent tools write to it; the endpoint drains it.

**Step 1: Write the test**

```python
# projects/monolith/chat/sse_test.py
import json
import pytest
from chat.sse import SSEEmitter


@pytest.mark.anyio
async def test_emit_and_drain():
    emitter = SSEEmitter()
    emitter.emit("node_discovered", {"note_id": "abc", "title": "Test"})
    emitter.emit("done", {})
    emitter.close()

    events = []
    async for chunk in emitter.stream():
        events.append(chunk)

    assert len(events) == 2
    first = json.loads(events[0].removeprefix("data: ").strip())
    assert first["type"] == "node_discovered"
    assert first["data"]["note_id"] == "abc"


@pytest.mark.anyio
async def test_close_terminates_stream():
    emitter = SSEEmitter()
    emitter.close()
    events = []
    async for chunk in emitter.stream():
        events.append(chunk)
    assert events == []
```

**Step 2: Run test to verify it fails**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:sse_test --config=ci
```

Expected: FAIL — module `chat.sse` does not exist.

**Step 3: Write the implementation**

```python
# projects/monolith/chat/sse.py
import asyncio
import json


class SSEEmitter:
    """Async queue-backed SSE event emitter.

    Tools call emit() to push events. The endpoint iterates stream()
    to drain them as text/event-stream lines.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()

    def emit(self, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, "data": data})
        self._queue.put_nowait(f"data: {payload}\n\n")

    def close(self) -> None:
        self._queue.put_nowait(None)

    async def stream(self):
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk
```

**Step 4: Run test to verify it passes**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:sse_test --config=ci
```

Expected: PASS

**Step 5: Add BUILD target** (gazelle should handle this, but verify)

```bash
format
```

**Step 6: Commit**

```bash
git add projects/monolith/chat/sse.py projects/monolith/chat/sse_test.py
git commit -m "feat(chat): add SSE emitter utility for streaming graph events"
```

---

### Task 3: Backend — PydanticAI explorer agent

**Files:**

- Create: `projects/monolith/chat/explorer.py`
- Create: `projects/monolith/chat/explorer_test.py`

This is the core agent with three tools. Each tool emits SSE events via the emitter in `ctx.deps`, then returns formatted text to Gemma.

**Step 1: Write the test for search_kg tool**

```python
# projects/monolith/chat/explorer_test.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from chat.explorer import create_explorer_agent, ExplorerDeps
from chat.sse import SSEEmitter


def make_deps(emitter: SSEEmitter) -> ExplorerDeps:
    store = MagicMock()
    store.search_notes_with_context.return_value = [
        {
            "note_id": "note-1",
            "title": "Kubernetes Networking",
            "type": "note",
            "tags": ["k8s", "networking"],
            "score": 0.92,
            "snippet": "Service mesh overview...",
            "edges": [
                {"target_id": "note-2", "target_title": "Linkerd", "kind": "edge", "edge_type": "refines"}
            ],
        }
    ]
    store.get_note_links.return_value = [
        {"target_id": "note-3", "target_title": "Cilium", "kind": "edge", "edge_type": "related"}
    ]
    store.get_note_by_id.return_value = {
        "note_id": "note-3",
        "title": "Cilium",
        "type": "article",
        "tags": ["networking"],
    }

    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.1] * 1024

    return ExplorerDeps(
        store=store,
        embed_client=embed_client,
        emitter=emitter,
    )


@pytest.mark.anyio
async def test_search_kg_emits_node_discovered():
    emitter = SSEEmitter()
    deps = make_deps(emitter)

    # Call the tool function directly
    from chat.explorer import _search_kg
    result = await _search_kg(deps, "kubernetes networking")

    emitter.close()
    events = []
    async for chunk in emitter.stream():
        parsed = json.loads(chunk.removeprefix("data: ").strip())
        events.append(parsed)

    assert len(events) == 1
    assert events[0]["type"] == "node_discovered"
    assert events[0]["data"]["note_id"] == "note-1"
    assert events[0]["data"]["title"] == "Kubernetes Networking"
    assert "refines" in str(events[0]["data"]["edges"])
    assert "kubernetes" in result.lower()


@pytest.mark.anyio
async def test_expand_node_emits_edge_and_node():
    emitter = SSEEmitter()
    deps = make_deps(emitter)

    from chat.explorer import _expand_node
    result = await _expand_node(deps, "note-1")

    emitter.close()
    events = []
    async for chunk in emitter.stream():
        parsed = json.loads(chunk.removeprefix("data: ").strip())
        events.append(parsed)

    types = [e["type"] for e in events]
    assert "edge_traversed" in types
    assert "node_discovered" in types


@pytest.mark.anyio
async def test_discard_node_emits_event():
    emitter = SSEEmitter()
    deps = make_deps(emitter)

    from chat.explorer import _discard_node
    result = await _discard_node(deps, "note-1", "not relevant to query")

    emitter.close()
    events = []
    async for chunk in emitter.stream():
        parsed = json.loads(chunk.removeprefix("data: ").strip())
        events.append(parsed)

    assert len(events) == 1
    assert events[0]["type"] == "node_discarded"
    assert events[0]["data"]["note_id"] == "note-1"
    assert events[0]["data"]["reason"] == "not relevant to query"
```

**Step 2: Run test to verify it fails**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:explorer_test --config=ci
```

Expected: FAIL — `chat.explorer` does not exist.

**Step 3: Write the implementation**

```python
# projects/monolith/chat/explorer.py
import os
from dataclasses import dataclass

from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from chat.sse import SSEEmitter
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

SYSTEM_PROMPT = """\
You are a knowledge graph explorer. The user asks questions and you search \
their personal knowledge graph to find relevant notes and connections.

Your workflow:
1. Use search_kg to find notes matching the user's question.
2. Use expand_node to follow edges from promising notes and discover connections.
3. Use discard_node to explicitly mark irrelevant results (with a reason).
4. Synthesize your findings into a clear answer, referencing the notes you found.

Always search before answering. Expand at least one promising node to discover \
deeper connections. Discard results that aren't relevant — be decisive. \
Reference notes by title when answering."""


@dataclass
class ExplorerDeps:
    store: KnowledgeStore
    embed_client: EmbeddingClient
    emitter: SSEEmitter


def create_explorer_agent() -> Agent[ExplorerDeps]:
    url = os.environ.get("LLAMA_CPP_URL", "http://localhost:8000")
    model = OpenAIChatModel(
        "gemma-4-26b-a4b",
        provider=OpenAIProvider(base_url=f"{url}/v1", api_key="not-needed"),
    )
    agent: Agent[ExplorerDeps] = Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        model_settings=ModelSettings(max_tokens=4096),
    )

    @agent.tool
    async def search_kg(ctx: RunContext[ExplorerDeps], query: str) -> str:
        """Semantic search across the knowledge graph. Returns matching notes."""
        return await _search_kg(ctx.deps, query)

    @agent.tool
    async def expand_node(ctx: RunContext[ExplorerDeps], note_id: str) -> str:
        """Follow edges from a node to discover connected notes."""
        return await _expand_node(ctx.deps, note_id)

    @agent.tool
    async def discard_node(
        ctx: RunContext[ExplorerDeps], note_id: str, reason: str
    ) -> str:
        """Mark a node as irrelevant to the current exploration."""
        return await _discard_node(ctx.deps, note_id, reason)

    return agent


async def _search_kg(deps: ExplorerDeps, query: str) -> str:
    vector = await deps.embed_client.embed(query)
    results = deps.store.search_notes_with_context(
        query_embedding=vector, limit=5
    )
    lines = []
    for r in results:
        deps.emitter.emit(
            "node_discovered",
            {
                "note_id": r["note_id"],
                "title": r["title"],
                "type": r["type"],
                "tags": r["tags"],
                "snippet": r["snippet"],
                "edges": r.get("edges", []),
            },
        )
        lines.append(
            f"- {r['title']} (score: {r['score']:.2f}, type: {r['type']}): "
            f"{r['snippet'][:200]}"
        )
    if not lines:
        return "No results found."
    return "Found notes:\n" + "\n".join(lines)


async def _expand_node(deps: ExplorerDeps, note_id: str) -> str:
    links = deps.store.get_note_links(note_id)
    if not links:
        return f"No edges found from {note_id}."

    lines = []
    for link in links:
        target_id = link.get("resolved_note_id") or link["target_id"]
        deps.emitter.emit(
            "edge_traversed",
            {
                "from_id": note_id,
                "to_id": target_id,
                "edge_type": link.get("edge_type", "link"),
            },
        )
        target = deps.store.get_note_by_id(target_id)
        if target:
            deps.emitter.emit(
                "node_discovered",
                {
                    "note_id": target["note_id"],
                    "title": target["title"],
                    "type": target["type"],
                    "tags": target.get("tags", []),
                    "snippet": "",
                    "edges": [],
                },
            )
            edge_label = link.get("edge_type", "link")
            lines.append(f"- {target['title']} ({edge_label})")
        else:
            lines.append(f"- {target_id} (unresolved)")

    return f"Edges from {note_id}:\n" + "\n".join(lines)


async def _discard_node(deps: ExplorerDeps, note_id: str, reason: str) -> str:
    deps.emitter.emit("node_discarded", {"note_id": note_id, "reason": reason})
    return f"Discarded {note_id}: {reason}"
```

**Step 4: Run tests**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:explorer_test --config=ci
```

Expected: PASS

**Step 5: Format and commit**

```bash
format
git add projects/monolith/chat/explorer.py projects/monolith/chat/explorer_test.py
git commit -m "feat(chat): add PydanticAI explorer agent with KG tools"
```

---

### Task 4: Backend — SSE streaming endpoint

**Files:**

- Modify: `projects/monolith/chat/router.py`
- Create: `projects/monolith/chat/explore_endpoint_test.py`

Wire the agent into a FastAPI endpoint that returns `text/event-stream`.

**Step 1: Write the test**

```python
# projects/monolith/chat/explore_endpoint_test.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    from app.main import app
    return TestClient(app)


def test_explore_returns_sse_content_type(client):
    with patch("chat.router.create_explorer_agent") as mock_agent_fn:
        mock_agent = MagicMock()
        mock_agent_fn.return_value = mock_agent

        # Mock run_stream to return an async context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        mock_stream.stream_text.return_value = AsyncMock()
        mock_agent.run_stream.return_value = mock_stream

        response = client.post(
            "/api/chat/explore",
            json={"message": "test query", "history": []},
        )
        assert response.headers["content-type"].startswith("text/event-stream")


def test_explore_rejects_empty_message(client):
    response = client.post(
        "/api/chat/explore",
        json={"message": "", "history": []},
    )
    assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:explore_endpoint_test --config=ci
```

Expected: FAIL — endpoint does not exist.

**Step 3: Write the endpoint**

Add to `projects/monolith/chat/router.py`:

```python
import asyncio
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from chat.explorer import ExplorerDeps, create_explorer_agent
from chat.sse import SSEEmitter
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient


class ExploreRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[dict] = Field(default_factory=list)


_explorer_agent = None


def get_explorer_agent():
    global _explorer_agent
    if _explorer_agent is None:
        _explorer_agent = create_explorer_agent()
    return _explorer_agent


@router.post("/explore")
async def explore(body: ExploreRequest, request: Request):
    session = next(get_session())
    emitter = SSEEmitter()
    agent = get_explorer_agent()

    deps = ExplorerDeps(
        store=KnowledgeStore(session),
        embed_client=EmbeddingClient(),
        emitter=emitter,
    )

    # Build message list from history + current message
    messages = []
    for turn in body.history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": body.message})

    async def generate():
        try:
            async with agent.run_stream(
                body.message,
                message_history=messages[:-1] if len(messages) > 1 else None,
                deps=deps,
            ) as stream:
                # Drain emitter events (from tool calls) concurrently with text
                async def drain_events():
                    async for chunk in emitter.stream():
                        yield chunk

                # Stream text chunks
                async for text in stream.stream_text(delta=True):
                    emitter.emit("text_chunk", {"text": text})

            emitter.emit("done", {})
            emitter.close()
        except Exception as e:
            emitter.emit("error", {"message": str(e)})
            emitter.close()

        async for event in emitter.stream():
            yield event

    return StreamingResponse(generate(), media_type="text/event-stream")
```

> **Note to implementer:** The concurrent streaming of tool-emitted events and text chunks is tricky. PydanticAI's `run_stream` calls tools synchronously during iteration. The emitter queue collects events from tools, and `stream_text(delta=True)` yields text deltas. Both types of events go through the emitter, so the `generate()` function just drains the emitter after the stream completes. If real-time interleaving is needed (tool events arrive _during_ text generation), refactor to use `asyncio.create_task` for the agent run and drain the emitter concurrently. Start with the simpler sequential approach and optimize if latency feels wrong.

**Step 4: Run tests**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith:explore_endpoint_test --config=ci
```

Expected: PASS

**Step 5: Format and commit**

```bash
format
git add projects/monolith/chat/router.py projects/monolith/chat/explore_endpoint_test.py
git commit -m "feat(chat): add /api/chat/explore SSE endpoint"
```

---

### Task 5: Frontend — Route skeleton and SSE proxy

**Files:**

- Create: `projects/monolith/frontend/src/routes/private/chat/+page.ts`
- Create: `projects/monolith/frontend/src/routes/private/chat/+server.js`
- Create: `projects/monolith/frontend/src/routes/private/chat/+page.svelte` (skeleton)

**Step 1: Create the SSR-disabled page loader**

```javascript
// projects/monolith/frontend/src/routes/private/chat/+page.ts
export const ssr = false;
```

**Step 2: Create the SSE proxy**

The `+server.js` file forwards POST requests to the FastAPI backend and streams the SSE response back to the browser.

```javascript
// projects/monolith/frontend/src/routes/private/chat/+server.js
const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function POST({ request }) {
  const body = await request.json();

  const upstream = await fetch(`${API_BASE}/api/chat/explore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    return new Response(JSON.stringify({ error: "upstream failed" }), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Pass through the SSE stream
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

**Step 3: Create the page skeleton**

```svelte
<!-- projects/monolith/frontend/src/routes/private/chat/+page.svelte -->
<script>
  // Minimal skeleton — will be fleshed out in subsequent tasks
  let messages = $state([]);
  let inputText = $state("");
  let isStreaming = $state(false);
</script>

<svelte:head>
  <title>Knowledge Explorer</title>
</svelte:head>

<div class="explorer">
  <header class="explorer-header">
    <span class="header-title">KNOWLEDGE EXPLORER</span>
    <span class="header-sub">powered by gemma-4</span>
  </header>

  <main class="explorer-body">
    <p style="font-family: monospace; padding: 2rem;">Page skeleton — chat and graph coming next.</p>
  </main>
</div>

<style>
  .explorer {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #faf8f4;
  }
  .explorer-header {
    background: #1a1a1a;
    color: #fff;
    font-family: monospace;
    padding: 0.5rem 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .header-title {
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .header-sub {
    opacity: 0.5;
    font-size: 0.8em;
  }
  .explorer-body {
    flex: 1;
    overflow: hidden;
  }
</style>
```

**Step 4: Verify the page loads locally** (if local dev server available) or just format and commit.

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/
git commit -m "feat(chat): add SvelteKit route skeleton with SSE proxy"
```

---

### Task 6: Frontend — Chat UI

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/chat/+page.svelte`

Build the chat card with input bar and streaming message display. No graph yet — just the chat portion.

**Step 1: Implement the chat UI and SSE consumer**

Replace the page skeleton with full chat implementation. Key pieces:

- `messages` array of `{role: "user"|"assistant", content: string}`
- `graphEvents` array of SSE graph events (consumed by graph in next task)
- `sendMessage()` function: POST to `+server.js`, parse SSE stream, append text chunks to assistant message, collect graph events
- Input bar with Enter-to-submit
- Scrollable chat log with brutalist styling

```svelte
<script>
  let messages = $state([]);
  let graphEvents = $state([]);
  let inputText = $state("");
  let isStreaming = $state(false);
  let chatLog;

  function scrollToBottom() {
    if (chatLog) chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function sendMessage() {
    const text = inputText.trim();
    if (!text || isStreaming) return;

    inputText = "";
    messages.push({ role: "user", content: text });
    messages.push({ role: "assistant", content: "" });
    isStreaming = true;
    scrollToBottom();

    try {
      const res = await fetch("/private/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: messages.slice(0, -2).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));

          if (event.type === "text_chunk") {
            messages[messages.length - 1].content += event.data.text;
            scrollToBottom();
          } else if (event.type === "error") {
            messages[messages.length - 1].content += `\n[Error: ${event.data.message}]`;
          } else if (event.type === "done") {
            // Stream complete
          } else {
            // Graph events — collected for the graph component
            graphEvents.push(event);
          }
        }
      }
    } catch (err) {
      messages[messages.length - 1].content += `\n[Connection error: ${err.message}]`;
    } finally {
      isStreaming = false;
    }
  }

  function onKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }
</script>
```

Template:

```svelte
<div class="explorer">
  <header class="explorer-header">
    <span class="header-title">KNOWLEDGE EXPLORER</span>
    <span class="header-sub">powered by gemma-4</span>
  </header>

  <div class="chat-card">
    <div class="chat-log" bind:this={chatLog}>
      {#each messages as msg}
        <div class="chat-msg chat-msg--{msg.role}">
          <span class="chat-role">{msg.role === "user" ? "you" : "gemma"}</span>
          <span class="chat-text">{msg.content}</span>
          {#if msg === messages[messages.length - 1] && isStreaming && msg.role === "assistant"}
            <span class="chat-cursor">|</span>
          {/if}
        </div>
      {/each}
    </div>
    <div class="chat-input-bar">
      <input
        type="text"
        bind:value={inputText}
        onkeydown={onKeydown}
        placeholder="explore your knowledge..."
        disabled={isStreaming}
      />
      <button onclick={sendMessage} disabled={isStreaming || !inputText.trim()}>
        &rarr;
      </button>
    </div>
  </div>

  <hr class="graph-rule" />
  <div class="graph-area">
    <!-- Graph canvas — Task 7+ -->
    {#if graphEvents.length === 0}
      <p class="graph-empty">Ask a question to start exploring</p>
    {/if}
  </div>
</div>
```

**Step 2: Add brutalist styles**

```css
.chat-card {
  margin: 1rem;
  border: 2px solid #1a1a1a;
  background: #f5f0e8;
  display: flex;
  flex-direction: column;
  max-height: 35vh;
  font-family: monospace;
}
.chat-log {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}
.chat-msg {
  margin-bottom: 0.75rem;
  line-height: 1.5;
}
.chat-msg--user {
  text-align: right;
}
.chat-msg--assistant {
  border-left: 3px solid #1a1a1a;
  padding-left: 0.75rem;
}
.chat-role {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.75em;
  letter-spacing: 0.05em;
  display: block;
  margin-bottom: 0.1rem;
  opacity: 0.5;
}
.chat-text {
  white-space: pre-wrap;
}
.chat-cursor {
  animation: blink 0.8s step-end infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.chat-input-bar {
  border-top: 2px solid #1a1a1a;
  display: flex;
}
.chat-input-bar input {
  flex: 1;
  padding: 0.75rem 1rem;
  font-family: monospace;
  font-size: 0.95rem;
  border: none;
  background: transparent;
  outline: none;
}
.chat-input-bar button {
  padding: 0.75rem 1.25rem;
  font-family: monospace;
  font-weight: 700;
  font-size: 1.1rem;
  border: none;
  border-left: 2px solid #1a1a1a;
  background: transparent;
  cursor: pointer;
}
.chat-input-bar button:disabled {
  opacity: 0.3;
  cursor: default;
}
.graph-rule {
  border: none;
  border-top: 1.5px solid #c0b8a8;
  margin: 0 1rem;
}
.graph-area {
  flex: 1;
  min-height: 0;
  overflow: auto;
  position: relative;
}
.graph-empty {
  font-family: monospace;
  text-align: center;
  padding: 3rem;
  opacity: 0.4;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
```

**Step 3: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/+page.svelte
git commit -m "feat(chat): implement chat UI with SSE streaming"
```

---

### Task 7: Frontend — Graph state and incremental dagre layout

**Files:**

- Create: `projects/monolith/frontend/src/routes/private/chat/graph-layout.js`

Extracted layout module that manages incremental graph state and dagre re-layout with position lerping.

**Step 1: Write the layout module**

```javascript
// projects/monolith/frontend/src/routes/private/chat/graph-layout.js
import * as dagre from "@dagrejs/dagre";

const CHAR_WIDTH = 6.5;
const NODE_PAD = 12;
const HH = 18;

function computeHW(label) {
  return Math.max(
    24,
    Math.ceil((label.length * CHAR_WIDTH) / 2) + NODE_PAD / 2,
  );
}

/**
 * Manages incremental graph layout.
 * Call addNode/addEdge as SSE events arrive, then call layout()
 * to get positioned nodes with smooth transitions.
 */
export function createGraphState() {
  let nodes = [];
  let edges = [];
  let nodeMap = {};
  let prevPositions = {};

  function addNode(node) {
    if (nodeMap[node.note_id]) return false; // Already exists
    const entry = {
      id: node.note_id,
      label: node.title,
      type: node.type,
      tags: node.tags || [],
      snippet: node.snippet || "",
      edges: node.edges || [],
      discarded: false,
      isNew: true,
    };
    nodes.push(entry);
    nodeMap[node.note_id] = entry;
    return true;
  }

  function addEdge(from_id, to_id, edge_type) {
    const exists = edges.some((e) => e.from === from_id && e.to === to_id);
    if (exists) return false;
    edges.push({ from: from_id, to: to_id, type: edge_type });
    return true;
  }

  function discardNode(note_id) {
    if (nodeMap[note_id]) {
      nodeMap[note_id].discarded = true;
    }
  }

  function layout() {
    // Save previous positions for lerping
    prevPositions = {};
    for (const n of nodes) {
      if (n.x !== undefined) {
        prevPositions[n.id] = { x: n.x, y: n.y };
      }
    }

    const g = new dagre.graphlib.Graph();
    g.setGraph({
      rankdir: "TB",
      nodesep: 50,
      ranksep: 60,
      marginx: 40,
      marginy: 40,
    });
    g.setDefaultEdgeLabel(() => ({}));

    for (const node of nodes) {
      const hw = computeHW(node.label);
      g.setNode(node.id, {
        width: hw * 2 + NODE_PAD,
        height: HH * 2 + 6,
      });
    }

    for (const edge of edges) {
      if (g.hasNode(edge.from) && g.hasNode(edge.to)) {
        g.setEdge(edge.from, edge.to);
      }
    }

    dagre.layout(g);

    const positioned = nodes.map((n) => {
      const pos = g.node(n.id);
      if (!pos) return n;
      const hw = computeHW(n.label);
      const prev = prevPositions[n.id];
      return {
        ...n,
        x: pos.x,
        y: pos.y,
        hw,
        prevX: prev?.x,
        prevY: prev?.y,
        isNew: prev === undefined,
      };
    });

    // Reset isNew after layout
    nodes.forEach((n) => (n.isNew = false));

    return {
      nodes: positioned,
      edges: edges.filter((e) => g.hasNode(e.from) && g.hasNode(e.to)),
      nodeMap,
    };
  }

  return { addNode, addEdge, discardNode, layout, getNodes: () => nodes };
}
```

**Step 2: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/graph-layout.js
git commit -m "feat(chat): add incremental dagre layout with position lerping"
```

---

### Task 8: Frontend — Rough.js graph rendering and animations

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/chat/+page.svelte`

Wire the graph state to an SVG canvas with rough.js rendering. Reuse the observability-demo's drawing patterns.

**Step 1: Add graph rendering**

Add to the `<script>` section:

- Import rough.js and the graph-layout module
- Create `graphState` using `createGraphState()`
- Add `$effect` that processes `graphEvents` queue: for each event, call `graphState.addNode/addEdge/discardNode`, then `graphState.layout()`, then draw with rough.js
- Position lerping: existing nodes use CSS `transition: transform 300ms ease-out`
- New nodes: pencil→ink→fill animation (simplified from observability-demo — single rough.js rectangle with opacity animation instead of the full 4-side sequential draw)
- Edge rendering: rough.js lines between node centers with arrowheads

**Color map by note type:**

```javascript
const TYPE_COLORS = {
  note: { fill: "#dbeafe", border: "#3b82f6", pencil: "#93c5fd" },
  paper: { fill: "#dcfce7", border: "#22c55e", pencil: "#86efac" },
  article: { fill: "#fef3c7", border: "#f59e0b", pencil: "#fcd34d" },
  recipe: { fill: "#ffe4e6", border: "#f43f5e", pencil: "#fda4af" },
};
```

**Key implementation detail:** Use `<g>` groups per node with `transform="translate(x, y)"` and CSS `transition: transform 300ms ease-out` for smooth position lerping. New nodes start with `opacity: 0` and animate in.

**Discarded nodes:** On discard, draw two `rc.line()` diagonals across the node and transition fill to grey.

**Step 2: Implement the SVG canvas in the template**

Replace the `<!-- Graph canvas — Task 7+ -->` placeholder with an `<svg>` element and the rough.js rendering `$effect`.

> **Note to implementer:** Reference `projects/monolith/frontend/src/routes/public/observability-demo/+page.svelte` for the exact rough.js patterns — how `rc = rough.svg(svgEl)` is created, how elements are appended to `<g>` groups, and how the animation CSS works. Simplify the 4-side sequential draw to a single rectangle draw for MVP — the full sequential animation can be added later.

**Step 3: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/+page.svelte
git commit -m "feat(chat): add rough.js graph rendering with smooth transitions"
```

---

### Task 9: Frontend — Hover highlights and click interactions

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/chat/+page.svelte`

**Step 1: Add interaction handlers**

- Transparent hit-area `<rect>` elements over each node (same pattern as observability-demo)
- `hoveredNode` state — on hover, highlight the node + connected edges (dim others to opacity 0.45)
- `selectedNode` state — on click, set selected and open the drawer
- Edge highlighting: connected edges get full opacity, others dim

**Step 2: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/+page.svelte
git commit -m "feat(chat): add hover highlights and click selection"
```

---

### Task 10: Frontend — Note drawer with markdown

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/chat/+page.svelte`
- Modify: `projects/monolith/frontend/src/routes/private/chat/+server.js` (add note fetch)

**Step 1: Add note fetch endpoint to +server.js**

Add a GET handler that proxies `/api/knowledge/notes/{id}`:

```javascript
export async function GET({ url }) {
  const noteId = url.searchParams.get("note_id");
  if (!noteId) return new Response("missing note_id", { status: 400 });

  const res = await fetch(
    `${API_BASE}/api/knowledge/notes/${encodeURIComponent(noteId)}`,
    { signal: AbortSignal.timeout(10000) },
  );
  return new Response(res.body, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
```

**Step 2: Add the drawer component**

In `+page.svelte`:

- When `selectedNode` is set, fetch the full note from the GET endpoint
- Render a slide-out drawer on the right (same pattern as observability-demo)
- Use `marked` to render the markdown body to HTML
- Display: title, type badge, tags, rendered markdown, outgoing edges list
- Dismiss on click-outside, Escape, or re-click

**Styling:**

```css
.note-drawer {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 420px;
  max-width: 90vw;
  background: #f5f0e8;
  border-left: 2px solid #1a1a1a;
  overflow-y: auto;
  padding: 1.5rem;
  font-family: monospace;
  z-index: 100;
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.1);
  transition: transform 200ms ease-out;
}
```

**Step 3: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/
git commit -m "feat(chat): add note drawer with markdown rendering"
```

---

### Task 11: Frontend — Dark/light theme support

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/chat/+page.svelte`

**Step 1: Add theme switching**

Reuse the observability-demo theme pattern:

- Read `localStorage.getItem("theme")` on mount
- Toggle via a button in the header bar
- CSS variables for light/dark variants
- Graph area uses warm cream (`#f5f0e8`) on both themes (same "light island" pattern from topology groups)
- Text, borders, and page background adapt to theme

**Step 2: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/chat/+page.svelte
git commit -m "feat(chat): add dark/light theme support"
```

---

### Task 12: Integration — Wire everything together and test end-to-end

**Files:**

- Possibly modify: `projects/monolith/app/main.py` (if router not auto-registered)
- Verify: all pieces connected

**Step 1: Verify router registration**

Check that `chat/router.py` is already included in `app/main.py` (it should be — the `/explore` endpoint is on the existing chat router). If not, add it.

**Step 2: Run all backend tests**

```bash
bb remote --os=linux --arch=amd64 test //projects/monolith/... --config=ci
```

Expected: All PASS.

**Step 3: Format check**

```bash
format
```

**Step 4: Manual end-to-end test** (if local dev available)

1. Start the monolith backend
2. Navigate to `localhost:5173/private/chat`
3. Type a query — verify SSE stream arrives
4. Verify nodes appear in graph
5. Click a node — verify drawer opens with markdown
6. Verify discarded nodes get strikethrough

**Step 5: Final commit and PR**

```bash
git add -A
git commit -m "feat(chat): knowledge graph explorer — integration wiring"
```

Use `superpowers:finishing-a-development-branch` skill to create PR.

---

## Task Summary

| Task | Component   | Description                               |
| ---- | ----------- | ----------------------------------------- |
| 1    | Dep         | Add `marked` for markdown rendering       |
| 2    | Backend     | SSE emitter utility                       |
| 3    | Backend     | PydanticAI explorer agent with 3 KG tools |
| 4    | Backend     | `/api/chat/explore` SSE endpoint          |
| 5    | Frontend    | SvelteKit route skeleton + SSE proxy      |
| 6    | Frontend    | Chat UI with SSE consumer                 |
| 7    | Frontend    | Incremental dagre layout module           |
| 8    | Frontend    | Rough.js graph rendering + animations     |
| 9    | Frontend    | Hover highlights + click interactions     |
| 10   | Frontend    | Note drawer with markdown                 |
| 11   | Frontend    | Dark/light theme                          |
| 12   | Integration | Wire together + test                      |

**Parallelizable:** Tasks 2-4 (backend) and Tasks 5-7 (frontend skeleton) can run in parallel since they don't share files. Tasks 8-11 are sequential frontend work. Task 12 is the final integration.
