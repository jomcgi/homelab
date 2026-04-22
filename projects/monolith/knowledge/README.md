# Knowledge Pipeline

LLM-powered knowledge graph with on-cluster inference.

## Overview

Raw markdown is ingested, decomposed into structured facts by Qwen-3 (with self-critique for quality), embedded with voyage-4-nano, and stored in pgvector for semantic search. Fronted by a SvelteKit app with a `Cmd+K` search overlay.

| Module              | Description                                                   |
| ------------------- | ------------------------------------------------------------- |
| **ingest_queue**    | Ingests raw markdown, routes to gardener or direct storage    |
| **raw_ingest**      | Discovers and processes raw markdown files from the vault     |
| **gardener**        | Qwen-3 fact decomposition with self-critique and distillation |
| **reconciler**      | Incremental re-embedding when the embedding model changes     |
| **store**           | pgvector-backed storage with semantic search                  |
| **service**         | FastAPI service layer                                         |
| **router**          | HTTP API routes                                               |
| **mcp**             | MCP tool exposure for AI agent access to the knowledge graph  |
| **links/wikilinks** | Obsidian wikilink parsing and backlink resolution             |
| **tasks_router**    | Task management API                                           |
