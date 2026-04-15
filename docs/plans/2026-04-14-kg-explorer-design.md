# Knowledge Graph Explorer Design

## Problem

The knowledge graph has semantic search and typed edges (refines, contradicts, derives_from, etc.) but no way to interactively explore it. Search results are flat lists — you can't see how concepts connect or watch the retrieval process unfold.

## Solution

A chat-driven knowledge graph explorer at `private.jomcgi.dev/chat`. The user asks questions, Gemma-4 searches and traverses the KG using tools, and a rough.js hand-drawn graph animates below the chat as nodes are discovered, connected, and discarded.

## Architecture

### SSE Event Protocol

A single SSE stream per user message carries interleaved text and graph events:

| Event             | Payload                                                                  | Trigger                                        |
| ----------------- | ------------------------------------------------------------------------ | ---------------------------------------------- |
| `node_discovered` | `{note_id, title, tags, type, snippet, edges: [{target_id, edge_type}]}` | Agent calls `search_kg` or `expand_node`       |
| `node_discarded`  | `{note_id, reason}`                                                      | Agent calls `discard_node`                     |
| `edge_traversed`  | `{from_id, to_id, edge_type}`                                            | Agent calls `expand_node`                      |
| `text_chunk`      | `{text}`                                                                 | Gemma streamed response tokens                 |
| `thinking`        | `{text}`                                                                 | Gemma reasoning_content (collapsed by default) |
| `done`            | `{}`                                                                     | Stream complete                                |
| `error`           | `{message}`                                                              | Failure                                        |

`node_discovered` includes outgoing edges so the frontend can draw connections between nodes already in the graph without a separate fetch. Edges to undiscovered nodes are deferred.

### Backend — PydanticAI Agent

**New file: `chat/explorer.py`**

A PydanticAI agent with Gemma-4 and three tools:

- **`search_kg(query)`** — Embed query via EmbeddingClient, vector search via KnowledgeStore. Emits `node_discovered` per result. Returns formatted results to Gemma.
- **`expand_node(note_id)`** — Fetch edges via KnowledgeStore.get_note_links(), fetch linked note metadata. Emits `edge_traversed` then `node_discovered` for new nodes. Returns edge summaries to Gemma.
- **`discard_node(note_id, reason)`** — Emits `node_discarded`. Returns confirmation to Gemma.

Each tool receives an SSE emitter via `ctx.deps` to push graph events onto the same stream as text tokens.

**New endpoint in `chat/router.py`:**

```
POST /api/chat/explore
Body: {"message": "...", "history": [...]}
Response: text/event-stream (SSE)
```

History array carries prior turns — no server-side session state. The system prompt instructs Gemma to search the KG before answering, expand promising nodes, discard irrelevant results explicitly, and synthesize answers referencing discovered nodes.

### Frontend — SvelteKit Page

**Route: `private/chat/`** — `+page.svelte` (SSR disabled), `+server.js` proxies SSE from FastAPI.

#### Layout

Brutalist / MotherDuck-inspired aesthetic:

- **Dark header bar** (`#1a1a1a`): "KNOWLEDGE EXPLORER — powered by gemma-4"
- **Chat card** (`#f5f0e8`, 2px hard border): scrollable message log + input bar at bottom. Gemma messages left-aligned with thin left-border accent, user messages right-aligned. Monospace throughout, uppercase headings.
- **Graph canvas** (below chat, separated by horizontal rules — no bounding box): rough.js SVG that grows unbounded as nodes are discovered. Scrolls vertically, pans horizontally.
- **Page background**: `#faf8f4` (slightly cooler than cards)

#### Graph Rendering

Rough.js hand-drawn nodes with pencil-to-ink-to-fill animation (reused from observability-demo). Nodes color-coded by note type:

- `note` — muted blue
- `paper` — muted green
- `article` — muted amber
- `recipe` — muted rose
- `discarded` — grey with rough.js diagonal strikethrough

Edge labels show relationship type in small monospace text at midpoint.

#### Incremental Layout with Smooth Transitions

Each `node_discovered` event triggers a dagre re-layout:

1. Add node to graph state
2. Re-run `dagre.layout()` with all current nodes + edges
3. Existing nodes: lerp from old position to new over 300ms (`transition: transform`)
4. New nodes: pencil-to-ink-to-fill animation
5. New edges: pencil-to-ink after both endpoints are drawn

Smooth position transitions are critical — the graph must not feel janky when dagre rearranges existing nodes to accommodate new ones.

#### Interactions

- **Hover**: highlight node + connected edges (same system as observability-demo)
- **Click node**: slide-out drawer from right with rendered markdown note content, metadata, tags, and outgoing edges list
- **Discarded nodes**: rough.js diagonal strikethrough, fill fades to grey, no longer interactive

#### Note Drawer

Same pattern as observability-demo detail drawer:

- Header: note title (uppercase monospace), type badge, tag pills
- Metadata: type, source, indexed date
- Body: rendered markdown (via `marked` or similar)
- Edges: outgoing edges grouped by type, clicking in-graph targets highlights them

2px hard border, warm cream background. Overlaps graph canvas with subtle shadow. Dismiss via click-outside, Escape, or re-click node.

## Persistence

**MVP: no persistence.** Refresh clears graph and chat. The feature is an exploration session, not a saved artifact.

**Future:** Server-side event storage with session IDs, replay endpoint for reconnection, localStorage for graceful recovery.

## Scope

### MVP

- Chat input with SSE streaming to Gemma-4 PydanticAI agent
- Three KG tools (search, expand, discard) emitting graph events
- Rough.js animated graph growing across chat turns
- Smooth dagre re-layout with position lerping
- Color-coded nodes by note type
- Rough.js strikethrough for discarded nodes
- Hover highlights, click opens note drawer with markdown
- Dark/light theme support (warm cream on both)
- Private route behind existing auth

### Not in scope

- Session persistence / replay
- Potential edge discovery on highlight (ghost nodes)
- Bring-into-context from unloaded edges
- Pinch-to-zoom / minimap
- Mobile-optimized layout
- Conversation history sidebar
- Sharing explorations

## Dependencies

- `roughjs` ^4.6.6 (existing)
- `@dagrejs/dagre` ^1.1.4 (existing)
- Markdown renderer (new frontend dep)
- PydanticAI (existing)
- FastAPI StreamingResponse or sse-starlette for SSE (check availability)

## Edge Map

```
user message → POST /api/chat/explore
  → PydanticAI agent.run_stream()
    → search_kg() → SSE: node_discovered (×N)
    → expand_node() → SSE: edge_traversed (×N), node_discovered (×N)
    → discard_node() → SSE: node_discarded
    → text generation → SSE: text_chunk (×N)
  → SSE: done
```
