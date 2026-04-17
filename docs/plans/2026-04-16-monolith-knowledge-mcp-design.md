# Monolith Knowledge MCP Endpoint

## Summary

Mount a FastMCP sub-app on the monolith at `/mcp`, exposing knowledge graph
search and note retrieval as MCP tools. Calls `KnowledgeStore` directly — no
HTTP proxy layer.

## Tools

| Tool                                     | Description                                 | Backing call                                                             |
| ---------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------ |
| `search_knowledge(query, limit?, type?)` | Semantic search over knowledge graph        | `EmbeddingClient.embed()` + `KnowledgeStore.search_notes_with_context()` |
| `get_note(note_id)`                      | Retrieve note metadata, markdown, and edges | `KnowledgeStore.get_note_by_id()` + vault file read + `get_note_links()` |

## Integration

- New file: `knowledge/mcp.py` — defines `FastMCP` instance and tool functions
- Mount: `app.mount("/mcp", mcp.http_app())` in `app/main.py`, before the static files mount
- DB sessions: tools use `Session(get_engine())` directly (scheduler pattern), not FastAPI `Depends()`
- Build: add `@pip//fastmcp` to `monolith_backend` deps in `BUILD`

## Out of scope

- Dead-letter / replay tools (can add later)
- Auto-registration with Context Forge (manual)
- Separate health endpoint (monolith `/healthz` suffices)
