# Knowledge Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose the monolith knowledge API on `private.jomcgi.dev` and build a Claude Code skill for searching/reading the Obsidian knowledge graph from a work laptop.

**Architecture:** Three layers of change: (1) Helm chart infra — add backend Service port + specific HTTPRoute rules, (2) Backend API — add edges to search and note-detail responses, (3) Claude Code skill — cloudflared auth + search → selective read workflow. TDD for backend changes, `helm template` validation for chart changes.

**Tech Stack:** Python (FastAPI, SQLModel, pgvector), Helm/Gateway API, Claude Code skills (Markdown), cloudflared

---

### Task 1: Add backend port to Service template

**Files:**

- Modify: `projects/monolith/chart/templates/service.yaml`
- Modify: `projects/monolith/chart/values.yaml` (add `service.apiPort`)

**Step 1: Add `apiPort` to chart values**

In `projects/monolith/chart/values.yaml`, add `apiPort` to the `service` block:

```yaml
service:
  port: 3000
  apiPort: 8000
```

**Step 2: Add backend port to Service template**

In `projects/monolith/chart/templates/service.yaml`, add a second port entry after the existing `http` port:

```yaml
- name: api
  port: { { .Values.service.apiPort } }
  targetPort: api
  protocol: TCP
```

The `targetPort: api` matches the container port name `api` on the backend container (`deployment.yaml:33`).

**Step 3: Validate with helm template**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A 10 'kind: Service'`

Expected: Service has two ports — `http` (3000) and `api` (8000).

**Step 4: Commit**

```bash
git add projects/monolith/chart/templates/service.yaml projects/monolith/chart/values.yaml
git commit -m "feat(monolith): expose backend API port in Service"
```

---

### Task 2: Add knowledge HTTPRoute rules

**Files:**

- Modify: `projects/monolith/chart/templates/httproute-private.yaml`

**Step 1: Add specific path rules before the catch-all**

Insert two rules after the `/_app/` rule and before the `# Everything else` catch-all in `projects/monolith/chart/templates/httproute-private.yaml`:

```yaml
# Knowledge API — pass through to backend without rewriting
- matches:
    - path:
        type: Exact
        value: /api/knowledge/search
  backendRefs:
    - name: { { include "monolith.fullname" . } }
      port: { { .Values.service.apiPort | int } }
- matches:
    - path:
        type: PathPrefix
        value: /api/knowledge/notes
  backendRefs:
    - name: { { include "monolith.fullname" . } }
      port: { { .Values.service.apiPort | int } }
```

**Step 2: Validate with helm template**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A 30 'httproute-private' | head -60`

Expected: Three rules visible before the catch-all: `/_app/`, `/api/knowledge/search` (Exact), `/api/knowledge/notes` (PathPrefix), then `/` (catch-all with rewrite).

**Step 3: Commit**

```bash
git add projects/monolith/chart/templates/httproute-private.yaml
git commit -m "feat(monolith): add knowledge API routes to private HTTPRoute"
```

---

### Task 3: Add `get_note_links` to KnowledgeStore

**Files:**

- Modify: `projects/monolith/knowledge/store.py`
- Test: `projects/monolith/knowledge/router_test.py`

**Step 1: Write the failing test**

Add to `projects/monolith/knowledge/router_test.py` inside the `TestSearchEndpoint` class:

```python
def test_search_results_include_edges(self, client, fake_embed_client):
    """Search results include edges from NoteLink table."""
    results_with_edges = [
        {
            **CANNED_RESULTS[0],
            "edges": [
                {"target_id": "n2", "kind": "edge", "edge_type": "refines", "target_title": None},
            ],
        },
    ]
    with patch("knowledge.router.KnowledgeStore") as MockStore:
        MockStore.return_value.search_notes_with_context.return_value = results_with_edges
        r = client.get("/api/knowledge/search?q=attention")

    assert r.status_code == 200
    result = r.json()["results"][0]
    assert "edges" in result
    assert result["edges"][0]["target_id"] == "n2"
    assert result["edges"][0]["edge_type"] == "refines"
```

Add a new test for the note detail endpoint in `TestGetNoteEndpoint`:

```python
def test_note_includes_edges(self, tmp_path, fake_session, monkeypatch):
    """Note detail response includes edges."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_file = vault_dir / "papers" / "attention.md"
    note_file.parent.mkdir(parents=True)
    note_file.write_text("# Attention\n\nContent.")

    monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
    app.dependency_overrides[get_session] = lambda: fake_session
    try:
        c = TestClient(app, raise_server_exceptions=False)
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.get_note_by_id.return_value = SAMPLE_NOTE
            MockStore.return_value.get_note_links.return_value = [
                {"target_id": "n2", "kind": "link", "edge_type": None, "target_title": "Related Note"},
            ]
            r = c.get("/api/knowledge/notes/n1")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert "edges" in body
    assert body["edges"][0]["target_id"] == "n2"
    assert body["edges"][0]["target_title"] == "Related Note"
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:knowledge_router_test --config=ci`

Expected: FAIL — `edges` key not in response, `get_note_links` not defined.

**Step 3: Add `get_note_links` method to KnowledgeStore**

In `projects/monolith/knowledge/store.py`, add after the `get_note_by_id` method:

```python
def get_note_links(self, note_id: str) -> list[dict]:
    """Fetch all outgoing links/edges for a note by its stable note_id."""
    note_fk = self.session.execute(
        select(Note.id).where(Note.note_id == note_id)
    ).scalar_one_or_none()
    if note_fk is None:
        return []
    rows = self.session.execute(
        select(
            NoteLink.target_id,
            NoteLink.target_title,
            NoteLink.kind,
            NoteLink.edge_type,
        ).where(NoteLink.src_note_fk == note_fk)
    ).all()
    return [
        {
            "target_id": row.target_id,
            "target_title": row.target_title,
            "kind": row.kind,
            "edge_type": row.edge_type,
        }
        for row in rows
    ]
```

**Step 4: Add edges to `search_notes_with_context`**

In `projects/monolith/knowledge/store.py`, inside `search_notes_with_context`, after the chunk stitching loop (after `best_chunk_by_note` is built), add a 3rd query:

```python
# 3. Batch-fetch edges for top-N notes.
edge_rows = self.session.execute(
    select(
        NoteLink.src_note_fk,
        NoteLink.target_id,
        NoteLink.target_title,
        NoteLink.kind,
        NoteLink.edge_type,
    ).where(NoteLink.src_note_fk.in_(top_ids))
).all()
edges_by_note: dict[int, list[dict]] = {}
for row in edge_rows:
    edges_by_note.setdefault(row.src_note_fk, []).append(
        {
            "target_id": row.target_id,
            "target_title": row.target_title,
            "kind": row.kind,
            "edge_type": row.edge_type,
        }
    )
```

Then update the results append to include edges:

```python
results.append(
    {
        "note_id": row.note_id,
        "title": row.title,
        "path": row.path,
        "type": row.type,
        "tags": list(row.tags or []),
        "score": float(row.score),
        "section": section,
        "snippet": (chunk_text or "")[:240],
        "edges": edges_by_note.get(row.id, []),
    }
)
```

**Step 5: Update the note detail router to include edges**

In `projects/monolith/knowledge/router.py`, update `get_knowledge_note`:

```python
@router.get("/notes/{note_id}")
def get_knowledge_note(
    note_id: str,
    session: Session = Depends(get_session),
) -> dict:
    store = KnowledgeStore(session)
    note = store.get_note_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
    resolved = (vault_root / note["path"]).resolve()
    if not resolved.is_relative_to(vault_root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="vault file missing")

    edges = store.get_note_links(note_id)
    return {**note, "content": resolved.read_text(), "edges": edges}
```

**Step 6: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:knowledge_router_test --config=ci`

Expected: All tests PASS including the two new edge tests.

**Step 7: Commit**

```bash
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/router.py projects/monolith/knowledge/router_test.py
git commit -m "feat(monolith): add edges to knowledge search and note-detail responses"
```

---

### Task 4: Bump chart version

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml`
- Modify: `projects/monolith/deploy/application.yaml`

**Step 1: Bump chart version**

In `projects/monolith/chart/Chart.yaml`, bump version from `0.31.29` to `0.32.0` (minor bump — new feature: backend API port + HTTPRoute rules).

**Step 2: Update targetRevision**

In `projects/monolith/deploy/application.yaml`, update `targetRevision` to match `0.32.0`.

**Step 3: Commit**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to 0.32.0"
```

---

### Task 5: Create the `/knowledge` skill

**Files:**

- Create: `.claude/skills/knowledge/SKILL.md`

**Step 1: Write the skill file**

Create `.claude/skills/knowledge/SKILL.md`:

````markdown
---
name: knowledge
description: >
  Search and read Joe's Obsidian knowledge graph. Use when ANY context about
  Joe's thinking, decisions, opinions, knowledge base, prior work, or personal
  notes might be relevant — even if there's only a 1% chance. Trigger examples:
  "What does Joe think about X?", "What's the basis for this?", "What do I mean
  by Y?", architectural decisions, project history, personal preferences.
---

# Knowledge Graph

Search and read notes from Joe's Obsidian vault via the monolith knowledge API.

## When to Use

- User asks what Joe thinks, means, or believes about a topic
- User references a past decision, project, or idea
- Context about Joe's knowledge or opinions would improve your response
- You need background on a topic Joe has written about
- ANY scenario where Joe's personal notes might be relevant

## Auth

The API is behind Cloudflare Access on `private.jomcgi.dev`.

**Get a token** (only needed once per session, or when token expires):

```bash
# Check if we have a valid token
TOKEN_FILE=$(ls -t ~/.cloudflared/*private.jomcgi.dev* 2>/dev/null | head -1)
if [ -z "$TOKEN_FILE" ]; then
  cloudflared access login https://private.jomcgi.dev
  TOKEN_FILE=$(ls -t ~/.cloudflared/*private.jomcgi.dev* 2>/dev/null | head -1)
fi
CF_TOKEN=$(cat "$TOKEN_FILE")
```
````

If a request returns 401/403 or a redirect to a login page, re-run
`cloudflared access login https://private.jomcgi.dev` and retry.

## API

Base URL: `https://private.jomcgi.dev`

### Search: `GET /api/knowledge/search`

```bash
curl -s -b "CF_Authorization=$CF_TOKEN" \
  "https://private.jomcgi.dev/api/knowledge/search?q=QUERY&limit=10"
```

Returns:

```json
{
  "results": [
    {
      "note_id": "abc",
      "title": "Note Title",
      "path": "folder/note.md",
      "type": "concept",
      "tags": ["tag1", "tag2"],
      "score": 0.85,
      "section": "## Section Header",
      "snippet": "First 240 chars of best-matching chunk...",
      "edges": [
        {
          "target_id": "def",
          "kind": "edge",
          "edge_type": "refines",
          "target_title": null
        },
        {
          "target_id": "ghi",
          "kind": "link",
          "edge_type": null,
          "target_title": "Linked Note"
        }
      ]
    }
  ]
}
```

### Read note: `GET /api/knowledge/notes/{note_id}`

```bash
curl -s -b "CF_Authorization=$CF_TOKEN" \
  "https://private.jomcgi.dev/api/knowledge/notes/NOTE_ID"
```

Returns full note content + edges.

## Workflow

1. **Formulate a search query** from the conversational context — use natural language
2. **Search** via the API — review results (title, tags, edges, snippet, score)
3. **Judge relevance** — only fetch full content for notes that look genuinely useful.
   Do NOT auto-fetch all results. Use the snippet and metadata to decide.
4. **Read selectively** — fetch full content for relevant notes via the notes endpoint
5. **Use the context** — reference it, quote it, or let it inform your reasoning

## Tips

- Search queries work best as natural language phrases, not keywords
- The `type` field indicates note category (concept, project, paper, etc.)
- Edges show how notes relate: `refines`, `generalizes`, `related`, `contradicts`, `derives_from`, `supersedes`
- `kind: "link"` = wikilink from note body; `kind: "edge"` = typed frontmatter relationship
- If search returns nothing useful, the query may just not match anything — that's fine, move on

````

**Step 2: Commit**

```bash
git add .claude/skills/knowledge/SKILL.md
git commit -m "feat: add knowledge graph skill for vault search and read"
````

---

### Task 6: Run full test suite and push

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`

Expected: All tests PASS.

**Step 2: Run format**

Run: `format` (in the worktree)

Expected: No changes, or auto-fixes applied.

**Step 3: Push and create PR**

```bash
git push -u origin feat/knowledge-skill
gh pr create --title "feat: knowledge graph skill + API routes" --body "..."
```
