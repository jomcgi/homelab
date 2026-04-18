# Knowledge Notes CRUD — Design

## Context

The monolith's knowledge module already handles search, retrieval, ingestion, and gardening. Note _creation_ currently proxies through vault-mcp (`POST /api/notes`), which we're deprecating. Edit and delete operations only exist on vault-mcp.

This design brings create/edit/delete into the monolith's knowledge module as both HTTP endpoints and MCP tools.

## API

### POST /api/knowledge/notes — Create a note

Request:

```json
{
  "content": "Markdown body",
  "title": "Optional Title",
  "source": "web-ui",
  "tags": ["optional"],
  "type": "atom"
}
```

Only `content` is required. The service generates YAML frontmatter, writes the file to the vault root. The existing `move_phase` catalogues it into `_raw/`, and `reconcile_raw_phase` creates DB records.

Response `201`:

```json
{ "path": "my-note-title.md" }
```

### PUT /api/knowledge/notes/{note_id} — Edit a note

Request:

```json
{
  "content": "Updated body",
  "title": "Updated Title",
  "tags": ["updated"]
}
```

Looks up the note via `KnowledgeStore`, resolves vault file path, overwrites with updated frontmatter and body. The reconciler picks up content hash changes on the next cycle.

Response `200`:

```json
{ "path": "path/to/note.md", "note_id": "the-note-id" }
```

### DELETE /api/knowledge/notes/{note_id} — Delete a note

Removes the file from the vault filesystem and deletes DB records (note, chunks, links).

Response `200`:

```json
{ "deleted": true, "note_id": "the-note-id" }
```

## MCP Tools

Three tools on the shared `mcp` instance in `knowledge/mcp.py`:

- `create_note(content, title?, source?, tags?, type?)` — same as POST
- `edit_note(note_id, content?, title?, tags?)` — same as PUT
- `delete_note(note_id)` — same as DELETE

## Service Layer

Functions in `knowledge/mcp.py` (or a helper if they grow):

- **create_note** — Build frontmatter YAML from optional fields, slugify title for filename, write `.md` to vault root. The move_phase handles the rest.
- **edit_note** — Look up note by ID via KnowledgeStore, resolve path under VAULT_ROOT, read existing file, merge updated fields into frontmatter, write back. Reconciler detects content hash change.
- **delete_note** — Look up note by ID, unlink file, delete Note/Chunk/NoteLink rows from DB.

## Cleanup

- Remove `notes/service.py` (vault-mcp proxy) and `notes/router.py`
- Remove notes router mount from `app/main.py`

## What Stays the Same

- `move_phase` — still scans vault root for `.md` files and catalogues into `_raw/`
- `reconcile_raw_phase` — still mirrors `_raw/` into DB
- Gardener — still decomposes raws into processed notes
- Reconciler — still embeds and syncs processed notes to pgvector
