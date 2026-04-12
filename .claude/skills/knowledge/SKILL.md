---
name: knowledge
description: >
  Search and read Joe's Obsidian knowledge graph, or debug ingest failures.
  Use when ANY context about Joe's thinking, decisions, opinions, knowledge base,
  prior work, or personal notes might be relevant — even if there's only a 1%
  chance. Also use for dead-lettered raws, gardener errors, or ingest debugging.
  Trigger examples: "What does Joe think about X?", "are there any dead letters?",
  "why didn't my note get processed?", architectural decisions, project history.
---

# Knowledge Graph

Query and debug the knowledge graph via the `homelab` CLI.

## When to Use

- User asks what Joe thinks, means, or believes about a topic
- User references a past decision, project, or idea
- Context about Joe's knowledge or opinions would improve your response
- Investigating failed knowledge ingestion or gardener processing errors
- Checking pipeline health after deploying gardener changes
- ANY scenario where Joe's personal notes might be relevant

## Commands

### Search notes

```bash
homelab knowledge search "query" [--limit N] [--type TYPE]
```

Returns compact one-liners with edges:

```
[0.85] dead-letter-queue — Dead Letter Queue Pattern (atom)
  derives_from→book-building-event-driven-microservices, related→exactly-once-delivery
```

### Read a note

```bash
homelab knowledge note <note_id>
```

Prints metadata to stdout, writes full markdown to a tmpfile.
Use `Read` on the tmpfile path to access content on demand.

### Check dead letters

```bash
homelab knowledge dead-letters
```

Lists raws that exhausted all retry attempts:

```
[42] _raw/2026/04/11/note.md (obsidian) — invalid JSON [3 retries]
```

### Replay a dead letter

```bash
homelab knowledge replay <raw_id>
```

Removes failed provenance so the gardener retries on its next cycle.

## Workflow

1. **Search** — formulate a natural language query
2. **Judge relevance** — use the compact output (score, title, edges) to decide what's useful
3. **Read selectively** — fetch full content only for relevant notes
4. **Traverse edges** — follow `derives_from` upstream for "why", `refines` downstream for detail

## Tips

- All commands support `--json` for raw API output
- Search queries work best as natural language phrases
- After replaying dead letters, re-check after the next gardener cycle
- Edge types: `refines`, `generalizes`, `related`, `contradicts`, `derives_from`, `supersedes`
- If auth fails, the CLI will prompt for `cloudflared access login` automatically
