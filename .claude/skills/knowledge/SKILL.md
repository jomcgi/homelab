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
