# iCal Feed Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hardcoded mock events in the monolith schedule panel with real iCal feed data, refreshed every 5 minutes.

**Architecture:** New `schedule/` package alongside `todo/` with a service that fetches an ICS feed via httpx, parses with `icalendar`, filters to today (America/Vancouver), and caches in memory. A FastAPI router exposes `GET /api/schedule/today`. The existing lifespan spawns an additional async task for the 5-minute poll. 1Password provides the feed URL via `OnePasswordItem` CRD.

**Tech Stack:** Python (icalendar, httpx), FastAPI, Helm (OnePasswordItem CRD), SvelteKit

---

### Task 1: Add icalendar dependency

**Files:**

- Modify: `pyproject.toml`
- Modify: `projects/monolith/BUILD` (srcs glob + py_library deps)

**Step 1: Add icalendar to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list under the `# Monolith dependencies` comment:

```python
"icalendar~=6.0",
```

**Step 2: Recompile requirements lock files**

```bash
cd /tmp/claude-worktrees/monolith-ical
uv pip compile pyproject.toml --extra-index-url=https://pypi.org/simple/ -o bazel/requirements/runtime.txt
```

Then regenerate `all.txt`:

```bash
uv pip compile pyproject.toml --extra-index-url=https://pypi.org/simple/ --all-extras -o bazel/requirements/all.txt
```

**Step 3: Add schedule/ to BUILD srcs glob and icalendar + httpx to deps**

In `projects/monolith/BUILD`, update both `py_venv_binary` and `py_library` srcs globs to include `"schedule/**/*.py"`, and add `@pip//icalendar` and `@pip//httpx` to the `py_library` deps list.

The `py_venv_binary` srcs glob becomes:

```python
srcs = glob(
    [
        "app/**/*.py",
        "schedule/**/*.py",
        "todo/**/*.py",
    ],
    exclude = ["**/*_test.py"],
),
```

Same for `py_library`. Add to `py_library` deps:

```python
"@pip//httpx",
"@pip//icalendar",
```

Add `# gazelle:exclude schedule` alongside the existing exclude directives at the top of the BUILD file.

**Step 4: Commit**

```bash
git add pyproject.toml bazel/requirements/runtime.txt bazel/requirements/all.txt projects/monolith/BUILD
git commit -m "build(monolith): add icalendar and httpx dependencies"
```

---

### Task 2: Schedule service — iCal parsing and caching

**Files:**

- Create: `projects/monolith/schedule/__init__.py` (empty)
- Create: `projects/monolith/schedule/service.py`

**Step 1: Write the failing test**

Create `projects/monolith/schedule/service_test.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from schedule.service import parse_events_for_date

TZ = ZoneInfo("America/Vancouver")

# Minimal ICS with one timed event and one all-day event
SAMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260330T090000
DTEND:20260330T093000
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260330
DTEND;VALUE=DATE:20260331
SUMMARY:Company Holiday
END:VEVENT
BEGIN:VEVENT
DTSTART:20260331T140000
DTEND:20260331T150000
SUMMARY:Tomorrow Event
END:VEVENT
END:VCALENDAR
"""


def test_parse_timed_event():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    timed = [e for e in events if not e["allDay"]]
    assert len(timed) == 1
    assert timed[0]["time"] == "09:00"
    assert timed[0]["title"] == "Standup"


def test_parse_all_day_event():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    all_day = [e for e in events if e["allDay"]]
    assert len(all_day) == 1
    assert all_day[0]["title"] == "Company Holiday"
    assert all_day[0]["time"] is None


def test_all_day_events_come_first():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    assert events[0]["allDay"] is True
    assert events[1]["allDay"] is False


def test_excludes_other_dates():
    events = parse_events_for_date(SAMPLE_ICS, date(2026, 3, 30), TZ)
    titles = [e["title"] for e in events]
    assert "Tomorrow Event" not in titles


def test_empty_calendar():
    ics = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
    events = parse_events_for_date(ics, date(2026, 3, 30), TZ)
    assert events == []
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:schedule_service_test` (via CI)
Expected: FAIL — `schedule.service` does not exist yet

**Step 3: Write minimal implementation**

Create `projects/monolith/schedule/__init__.py` (empty file).

Create `projects/monolith/schedule/service.py`:

```python
import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Vancouver")

# In-memory cache, populated by poll_calendar()
_cached_events: list[dict] = []

ICAL_FEED_URL = os.environ.get("ICAL_FEED_URL", "")


def parse_events_for_date(
    ics_text: str, target_date: date, tz: ZoneInfo
) -> list[dict]:
    cal = Calendar.from_ical(ics_text)
    all_day = []
    timed = []

    for component in cal.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        dt = dtstart.dt
        summary = str(component.get("SUMMARY", ""))

        # All-day event: dtstart is a date, not datetime
        if isinstance(dt, date) and not isinstance(dt, datetime):
            if dt == target_date:
                all_day.append({"time": None, "title": summary, "allDay": True})
            continue

        # Timed event: convert to target timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)

        if dt.date() == target_date:
            timed.append({
                "time": dt.strftime("%H:%M"),
                "title": summary,
                "allDay": False,
            })

    timed.sort(key=lambda e: e["time"])
    return all_day + timed


def get_today_events() -> list[dict]:
    return list(_cached_events)


async def poll_calendar() -> None:
    global _cached_events
    if not ICAL_FEED_URL:
        logger.warning("ICAL_FEED_URL not set, skipping calendar poll")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(ICAL_FEED_URL, timeout=30)
            resp.raise_for_status()
        today = datetime.now(TZ).date()
        _cached_events = parse_events_for_date(resp.text, today, TZ)
        logger.info("Calendar refreshed: %d events for %s", len(_cached_events), today)
    except Exception:
        logger.exception("Failed to fetch calendar feed")
```

**Step 4: Run test to verify it passes**

Run: `bazel test //projects/monolith:schedule_service_test`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/schedule/
git commit -m "feat(monolith): add iCal parsing service with in-memory cache"
```

---

### Task 3: Schedule router

**Files:**

- Create: `projects/monolith/schedule/router.py`

**Step 1: Write the failing test**

Create `projects/monolith/schedule/router_test.py`:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

MOCK_EVENTS = [
    {"time": None, "title": "Holiday", "allDay": True},
    {"time": "09:00", "title": "Standup", "allDay": False},
]


@pytest.fixture(name="client")
def client_fixture():
    return TestClient(app, raise_server_exceptions=False)


def test_schedule_today_returns_events(client):
    with patch("schedule.service.get_today_events", return_value=MOCK_EVENTS):
        response = client.get("/api/schedule/today")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["allDay"] is True
    assert data[1]["time"] == "09:00"


def test_schedule_today_empty(client):
    with patch("schedule.service.get_today_events", return_value=[]):
        response = client.get("/api/schedule/today")
    assert response.status_code == 200
    assert response.json() == []
```

**Step 2: Run test to verify it fails**

Expected: FAIL — router does not exist, route not registered

**Step 3: Write minimal implementation**

Create `projects/monolith/schedule/router.py`:

```python
from fastapi import APIRouter

from .service import get_today_events

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/today")
def schedule_today() -> list[dict]:
    return get_today_events()
```

Then register the router in `projects/monolith/app/main.py`. Add after the todo_router import:

```python
from schedule.router import router as schedule_router
```

And after `app.include_router(todo_router)`:

```python
app.include_router(schedule_router)
```

**Step 4: Run test to verify it passes**

Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/schedule/router.py projects/monolith/schedule/router_test.py projects/monolith/app/main.py
git commit -m "feat(monolith): add GET /api/schedule/today router"
```

---

### Task 4: Wire up the 5-minute poll in lifespan

**Files:**

- Modify: `projects/monolith/app/main.py`

**Step 1: Update lifespan to spawn calendar poll task**

Modify the `lifespan` function in `projects/monolith/app/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from schedule.service import poll_calendar

    # Initial fetch, then poll every 5 minutes
    async def calendar_loop():
        while True:
            await poll_calendar()
            await asyncio.sleep(300)

    scheduler_task = asyncio.create_task(run_scheduler())
    calendar_task = asyncio.create_task(calendar_loop())
    logger.info("Monolith started")
    yield
    calendar_task.cancel()
    scheduler_task.cancel()
    logger.info("Monolith shutting down")
```

**Step 2: Commit**

```bash
git add projects/monolith/app/main.py
git commit -m "feat(monolith): poll iCal feed every 5 minutes on startup"
```

---

### Task 5: Add BUILD test targets

**Files:**

- Modify: `projects/monolith/BUILD`

**Step 1: Add test targets for schedule tests**

Add to `projects/monolith/BUILD`:

```python
py_test(
    name = "schedule_service_test",
    srcs = ["schedule/service_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//icalendar",
        "@pip//pytest",
        "@pip//tzdata",
    ],
)

py_test(
    name = "schedule_router_test",
    srcs = ["schedule/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//tzdata",
    ],
)
```

**Step 2: Run tests**

```bash
bazel test //projects/monolith:schedule_service_test //projects/monolith:schedule_router_test
```

Expected: PASS

**Step 3: Commit**

```bash
git add projects/monolith/BUILD
git commit -m "test(monolith): add BUILD targets for schedule tests"
```

---

### Task 6: Helm chart — 1Password secret and env var

**Files:**

- Create: `projects/monolith/chart/templates/onepassworditem.yaml`
- Modify: `projects/monolith/chart/templates/deployment.yaml`
- Modify: `projects/monolith/chart/values.yaml`
- Modify: `projects/monolith/deploy/values.yaml`

**Step 1: Create OnePasswordItem template**

Create `projects/monolith/chart/templates/onepassworditem.yaml`:

```yaml
{{- if .Values.onepassword.enabled }}
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: {{ include "monolith.fullname" . }}-secrets
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "monolith.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.onepassword.itemPath | quote }}
{{- end }}
```

**Step 2: Add ICAL_FEED_URL env var to deployment**

In `projects/monolith/chart/templates/deployment.yaml`, add after the DATABASE_URL env var:

```yaml
            {{- if .Values.onepassword.enabled }}
            - name: ICAL_FEED_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "monolith.fullname" . }}-secrets
                  key: ICAL_FEED_URL
            {{- end }}
```

**Step 3: Add default values to chart values.yaml**

In `projects/monolith/chart/values.yaml`, add:

```yaml
onepassword:
  enabled: false
  itemPath: ""
```

**Step 4: Set deploy values**

In `projects/monolith/deploy/values.yaml`, add:

```yaml
onepassword:
  enabled: true
  itemPath: "vaults/Homelab/items/private-homepage"
```

**Step 5: Bump chart version**

Bump `projects/monolith/chart/Chart.yaml` version (e.g. `0.5.4` → `0.5.5`) and update `projects/monolith/deploy/application.yaml` `targetRevision` to match.

**Step 6: Commit**

```bash
git add projects/monolith/chart/ projects/monolith/deploy/
git commit -m "feat(monolith): add 1Password secret for iCal feed URL"
```

---

### Task 7: Frontend — fetch and render schedule from API

**Files:**

- Modify: `projects/monolith/frontend/src/routes/+page.js`
- Modify: `projects/monolith/frontend/src/routes/+page.svelte`

**Step 1: Fetch schedule data in page loader**

Update `projects/monolith/frontend/src/routes/+page.js`:

```javascript
export async function load({ fetch }) {
  const [todoRes, scheduleRes] = await Promise.all([
    fetch("/api/todo", { signal: AbortSignal.timeout(10000) }),
    fetch("/api/schedule/today", { signal: AbortSignal.timeout(10000) }).catch(
      () => ({ ok: false }),
    ),
  ]);
  return {
    todo: await todoRes.json(),
    schedule: scheduleRes.ok ? await scheduleRes.json() : [],
  };
}
```

**Step 2: Update +page.svelte to use API data**

In `projects/monolith/frontend/src/routes/+page.svelte`, replace the hardcoded `EVENTS` constant with:

```javascript
let events = $state(data.schedule);
```

Update the Schedule section template to use `events` instead of `EVENTS`, and handle all-day events:

```svelte
<!-- Schedule -->
<section class="panel-section">
  <h2 class="section-label">today</h2>
  <ul class="event-list">
    {#each events as ev}
      <li class="event-row" class:event-row--past={!ev.allDay && isPast(ev.time, now)}>
        {#if ev.allDay}
          <span class="event-time"></span>
          <span class="event-title">{ev.title}</span>
          <span class="event-meta">all day</span>
        {:else}
          <span class="event-time">{ev.time}</span>
          <span class="event-title">{ev.title}</span>
          <span class="event-meta"></span>
        {/if}
      </li>
    {/each}
  </ul>
</section>
```

Remove the hardcoded `EVENTS` array and the `isPast` function's dependency on `meta` field — it only needs `time`.

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/routes/
git commit -m "feat(monolith): render live calendar events from iCal feed"
```

---

### Task 8: Push, PR, and deploy

**Step 1: Push branch**

```bash
git push -u origin feat/monolith-ical
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(monolith): integrate iCal feed for schedule panel" --body "..."
```

**Step 3: Enable auto-merge, monitor CI, verify deployment**

```bash
gh pr merge --auto --rebase
```

After merge, trigger ArgoCD sync if needed and verify `private.jomcgi.dev` shows real calendar events.
