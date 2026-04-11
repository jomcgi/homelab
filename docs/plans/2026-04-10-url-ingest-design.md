# URL Ingest: YouTube Transcripts & Webpage Articles

**Date:** 2026-04-10
**Status:** Approved

## Problem

The knowledge pipeline only ingests content dropped into the Obsidian vault as `.md` files. There's no way to feed it a YouTube video or blog post URL and have the content extracted, decomposed, and searchable.

## Solution

Add a Postgres-backed ingest queue and a scheduled fetcher job. The user pastes a URL on the homepage capture pane (toggled via `Cmd+I`), it gets queued, and a background job fetches the content and writes it to `_raw/` where the existing gardener pipeline takes over.

## Data Model

New table `knowledge.ingest_queue`:

```sql
CREATE TABLE knowledge.ingest_queue (
    id           BIGSERIAL PRIMARY KEY,
    url          TEXT NOT NULL,
    source_type  TEXT NOT NULL CHECK (source_type IN ('youtube', 'webpage')),
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at   TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

CREATE INDEX ingest_queue_status ON knowledge.ingest_queue (status)
    WHERE status = 'pending';
```

Rows are never deleted — the queue doubles as an audit log. A row stuck in `processing` for >5 minutes is considered stale and re-claimable (TTL pattern).

### Claim query

```sql
UPDATE knowledge.ingest_queue
SET status = 'processing', started_at = NOW()
WHERE id = (
    SELECT id FROM knowledge.ingest_queue
    WHERE status = 'pending'
       OR (status = 'processing' AND started_at < NOW() - INTERVAL '5 minutes')
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

`FOR UPDATE SKIP LOCKED` ensures only one pod claims each row — no advisory locks needed.

### Output format

Fetched content is written to `_raw/YYYY/MM/DD/<hash>-<slug>.md` with frontmatter:

```yaml
---
title: "Video or Article Title"
source: youtube # or webpage
original_url: https://...
---
<transcript or article markdown>
```

The existing `move_phase` -> `reconcile_raw_phase` -> gardener pipeline handles everything from there.

## Backend

### New file: `knowledge/ingest_queue.py`

- `IngestQueueItem` SQLModel table model
- `fetch_youtube(url) -> (title, markdown)` — uses `youtube-transcript-api`
- `fetch_webpage(url) -> (title, markdown)` — uses `trafilatura` with `output_format="markdown"`
- `ingest_handler(session)` — scheduler handler: claim one row, fetch, write to `_raw/`, mark done/failed

### Changes to existing files

- `knowledge/router.py` — add `POST /api/knowledge/ingest` endpoint (accepts `{url, source_type}`, inserts queue row, returns `{queued: true}`)
- `knowledge/service.py` — register `knowledge.ingest` scheduler job in `on_startup()`, same 5-minute interval as gardener/reconciler

### New dependencies

- `youtube-transcript-api` (via `@pip//youtube_transcript_api`)
- `trafilatura` (via `@pip//trafilatura`)

## Frontend

### Capture pane: ingest mode toggle

- `Cmd+I` toggles between note mode (default) and ingest mode
- Ingest mode changes:
  - Placeholder: `paste url...` (instead of `write something...`)
  - Footer left: mode indicator auto-detected from URL content (`youtube` if URL matches `youtube.com`/`youtu.be`, `webpage` otherwise)
  - Footer hint: `⌘I` (to toggle back) + `⌘ enter` (to submit)
- `Cmd+Enter` submits to `?/ingest` form action -> `POST /api/knowledge/ingest`
- Same `sent` flash as notes, then clears back to note mode

### No other UI changes

No progress indicators, no queue viewer, no settings. Fire-and-forget.

## Decisions

- **Queue grows forever** — rows are never deleted. Failed items stay for debugging, done items serve as history. Can add cleanup later if needed.
- **5-minute TTL** — matches the scheduler interval. A stuck `processing` row is re-claimable after 5 minutes.
- **One item per tick** — the handler claims and processes one URL per scheduler cycle. Keeps things simple and avoids overwhelming external services.
- **No URL validation** — if the fetch fails, it fails into the `error` column. No need to validate URL format beyond Pydantic's `str`.
- **Auto-detect source type from URL** — frontend detects YouTube vs webpage from the URL pattern. No manual type picker.
- **trafilatura for webpages** — best markdown output for technical blog posts. Preserves headings, code blocks, lists.
