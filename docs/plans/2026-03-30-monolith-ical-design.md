# Monolith iCal Feed Integration Design

## Goal

Replace hardcoded mock events in the private.jomcgi.dev schedule panel with real calendar data from an iCal feed, refreshed every 5 minutes.

## Data Flow

```
iCal feed URL (1Password "private-homepage" → ICAL_FEED_URL env var)
        ↓
Backend scheduler (every 5min)
  → fetch ICS via httpx → parse with icalendar lib
  → filter to today (America/Vancouver)
  → cache in memory
        ↓
GET /api/schedule/today
  → return cached events [{time, title, allDay}]
        ↓
Frontend fetches on page load alongside /api/todo
  → renders in existing Schedule section
  → all-day events at top (no time), timed events sorted by start
  → past events get strikethrough (existing behavior)
```

## Backend

- New `schedule/` package alongside `todo/`
- `schedule/service.py`: fetches ICS URL, parses with `icalendar`, filters to today in America/Vancouver, caches in module-level variable
- `schedule/router.py`: `GET /api/schedule/today` returns `[{time: "09:00", title: "Standup", allDay: false}]`
- All-day events: `{time: null, title: "Holiday", allDay: true}`
- Timed events: duration derived from start/end not needed in API (frontend only needs start time for strikethrough logic)
- Scheduler polls every 5 minutes (added to existing `run_scheduler` or parallel task in lifespan)
- ICS feed URL from `ICAL_FEED_URL` env var

## Secrets

- 1Password item: `private-homepage` with `ICAL_FEED_URL` field
- `OnePasswordItem` CRD in Helm chart templates
- Env var `ICAL_FEED_URL` on the deployment

## Frontend

- `+page.js`: fetch `/api/schedule/today` alongside `/api/todo`
- Replace hardcoded `EVENTS` and `LINKS` arrays with API data (events only; links stay hardcoded for now)
- All-day events rendered at top with no time column
- Timed events sorted by start time, past events get strikethrough
- Graceful fallback: if API returns empty or errors, show empty schedule section

## Dependencies

- `icalendar` — iCal parser (add to pyproject.toml + BUILD)
- `httpx` — already in repo

## Scope Boundaries

- No write operations (read-only feed)
- No multi-calendar support (single feed URL)
- No caching to database (memory only, repopulates on pod restart)
- Links grid stays hardcoded (separate feature)
