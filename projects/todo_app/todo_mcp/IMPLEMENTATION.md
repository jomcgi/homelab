# TODO App Implementation Guide

A minimalist, git-backed todo tracker with weekly focus and daily top 3.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Public (Cloudflare Tunnel)              │
│  todo.jomcgi.dev                                            │
│    └── /*          → nginx (static site from /public)       │
├─────────────────────────────────────────────────────────────┤
│                  Private (Zero Trust)                       │
│  todo-admin.jomcgi.dev                                      │
│    ├── /           → edit UI                                │
│    ├── /api/weekly → GET { task, done }                     │
│    ├── /api/daily  → GET [{ task, done }, ...]              │
│    ├── /api/todo   → PUT full state                         │
│    └── /api/reset/* → POST triggers                         │
├─────────────────────────────────────────────────────────────┤
│                  Internal Scheduler                         │
│    └── Go goroutine handles daily/weekly resets at PST      │
├─────────────────────────────────────────────────────────────┤
│                    Persistence                              │
│    └── git repo    → current state + historical markdown    │
└─────────────────────────────────────────────────────────────┘
```

## Data Contract

### Current State: `data.json`

```json
{
  "weekly": { "task": "string", "done": false },
  "daily": [
    { "task": "string", "done": false },
    { "task": "string", "done": false },
    { "task": "string", "done": false }
  ]
}
```

### Historical: `/{YYYY}/{MM}/{D}.md`

```markdown
# Thursday, January 30

## Weekly

Ship Cloudflare operator v0.1

## Daily

- [x] Fix ArgoCD sync timeout on staging
- [x] Write CRD validation for tunnel annotations
- [ ] Review PR for metrics aggregation
```

### API Endpoints

| Endpoint            | Method | Request           | Response                                 |
| ------------------- | ------ | ----------------- | ---------------------------------------- |
| `/api/weekly`       | GET    | -                 | `{ task: string, done: boolean }`        |
| `/api/daily`        | GET    | -                 | `[{ task: string, done: boolean }, ...]` |
| `/api/todo`         | PUT    | Full state object | 200 OK                                   |
| `/api/reset/daily`  | POST   | -                 | Archives day, clears daily               |
| `/api/reset/weekly` | POST   | -                 | Archives day, clears all                 |
| `/api/dates`        | GET    | -                 | `string[]` ISO dates, max 14 days        |

## Design System

### Theme: Catppuccin Latte

```css
:root {
  --base: #eff1f5; /* background */
  --text: #4c4f69; /* primary text, active tasks */
  --subtext: #6c6f85; /* section headers */
  --surface: #ccd0da; /* borders */
  --muted: #bcc0cc; /* empty placeholders */
  --green: #40a02b; /* done tasks */
  --red: #d20f39; /* action prompts */
}
```

### Color Usage

| Element         | Color       | Notes                        |
| --------------- | ----------- | ---------------------------- |
| Active tasks    | `--text`    | Primary focus                |
| Done tasks      | `--green`   | + strikethrough, 60% opacity |
| Empty slots     | `--muted`   | Shows "..."                  |
| Section headers | `--subtext` | WEEKLY, DAILY                |
| Action prompts  | `--red`     | "@jomcgi set your week"      |
| Prompt hover    | `--text`    | Red fades to neutral         |
| Borders         | `--surface` | Subtle separators            |
| Background      | `--base`    | Light cream                  |

### Typography

- Font: `monospace` (system)
- Title: 1.5rem, letter-spacing 0.2em
- Headers: 1rem, letter-spacing 0.1em
- Tasks: 1.1rem
- Max width: 600px, centered

### Visual Rules

1. **No checkmarks** — strikethrough indicates done
2. **No numbers** — order implies priority
3. **No date on today** — only shows when viewing history
4. **No visible nav** — arrow keys work, no buttons shown
5. **No subtitles** — "the one thing that matters" etc removed

## Empty States

When weekly is empty:

```
@jomcgi set your week
```

When all daily tasks are empty:

```
@jomcgi set your day
...
...
```

Both link to `https://todo-admin.jomcgi.dev`

## File Structure

Following the homelab repo colocation principle - service code lives inside its chart:

```
charts/todo/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── pvc.yaml
│   └── configmap.yaml          # Static HTML files
├── src/                        # Colocated Go source
│   ├── main.go
│   └── go.mod
├── static/
│   ├── index.html              # Public view (build template)
│   └── edit.html               # Admin edit UI
└── Dockerfile

overlays/prod/todo/
├── application.yaml            # ArgoCD Application
├── kustomization.yaml
└── values.yaml                 # Environment overrides (git repo, etc)
```

### Data Directory (at runtime)

```
/data/
├── data.json                   # Current state
├── public/                     # Built output (served by nginx)
│   ├── index.html              # With dates injected
│   ├── data.json
│   └── {YYYY}/{MM}/{D}.md      # Historical (14-day window only)
└── {YYYY}/
    └── {MM}/
        └── {D}.md              # Full archive (all history in git)
```

## Build Process

On reset (daily or weekly):

1. Archive current state to `{YYYY}/{MM}/{D}.md`
2. Clear appropriate fields in `data.json`
3. Collect dates within 14-day rolling window
4. Inject dates array into `static/index.html` template
5. Copy to `public/` directory
6. Copy only markdown files within window to `public/`
7. Git commit and push

### Date Injection

Template contains:

```javascript
const DATES = /*DATES_PLACEHOLDER*/ [
  "2025-01-28",
  "2025-01-29",
  "2025-01-30",
]; /*END_PLACEHOLDER*/
```

Build replaces with actual dates array.

## Kubernetes Resources

### Deployment

- **Init container**: Clone/pull git repo
- **API container**: Go server on :8080 (includes internal scheduler)
- **Static container**: nginx on :80, serves `/public`
- **Volume**: PVC for data, git SSH secret

### Services

- `todo-public`: Port 80 → nginx, public Cloudflare tunnel
- `todo-admin`: Port 8080 → API, Zero Trust protected

### Internal Scheduler

The Go service runs its own scheduler (no CronJobs needed):

```go
func startScheduler() {
    loc, _ := time.LoadLocation("America/Los_Angeles")

    go func() {
        for {
            now := time.Now().In(loc)

            // Calculate next midnight PST
            next := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, loc)
            time.Sleep(time.Until(next))

            // Saturday midnight = end of Friday
            if time.Now().In(loc).Weekday() == time.Saturday {
                resetWeekly()
            } else {
                resetDaily()
            }
        }
    }()
}
```

Called from `main()` after server setup.

## Frontend Behavior

### Today View

1. Fetch `/api/weekly` and `/api/daily` in parallel
2. Render tasks or empty state prompts
3. No date shown in header

### Historical View

1. Fetch `/{YYYY}/{MM}/{D}.md`
2. Parse markdown for weekly and daily sections
3. Show date in header (e.g., "Wednesday, January 29")

### Navigation

- Left arrow: Previous day (if available)
- Right arrow: Next day (if not at today)
- No visible buttons

### Fallback

- If API fails, try `data.json` static file
- If historical fetch fails, show empty state

## Admin UI Behavior

1. Load current state on page load
2. Debounced auto-save (500ms after last change)
3. Checkboxes for done state
4. Text inputs for tasks
5. Manual reset buttons with confirmation
6. Status indicator: saving... / saved / error

## Git Integration

### Environment Variables

- `GIT_REPO`: SSH URL (e.g., `git@github.com:jomcgi/todo.git`)
- `GIT_BRANCH`: Branch name (default: `main`)
- `DATA_DIR`: Data directory path (default: `/data`)

### Commit Messages

- Daily reset: `reset: daily`
- Weekly reset: `reset: weekly`

### SSH Key

Mounted from secret at `/root/.ssh`, mode 0400.

## Rolling Window

- **Web accessible**: 14 days only
- **Git archive**: All history preserved
- **Cleanup**: Old files stay in git, just not served
- **Dates endpoint**: Returns only dates within window

## Example States

### Fresh Week (Monday morning)

```
WEEKLY
@jomcgi set your week

DAILY
@jomcgi set your day
...
...
```

### Mid-Week Active

```
WEEKLY
Ship Cloudflare operator v0.1

DAILY
Fix ArgoCD sync timeout on staging  [done, green, strikethrough]
Write CRD validation for tunnel annotations
...
```

### End of Day (all done)

```
WEEKLY
Ship Cloudflare operator v0.1

DAILY
Fix ArgoCD sync timeout on staging  [done]
Write CRD validation
Review PR for metrics aggregation    [done]
```

## Implementation Checklist

### Chart Setup

- [x] Create `charts/todo/Chart.yaml`
- [x] Create `charts/todo/values.yaml` with defaults
- [x] Create `charts/todo/templates/` (deployment, service, pvc)

### Source Code (in `charts/todo/src/`)

- [x] Go API server with all endpoints
- [x] Internal scheduler for daily/weekly resets
- [x] Git clone/pull in init logic (deployment init container)
- [x] Git commit/push on reset
- [x] Date injection build step
- [x] 14-day window filtering
- [x] Markdown archive format

### Static Files (in `charts/todo/static/`)

- [x] index.html with Catppuccin Latte theme
- [x] edit.html for admin

### Overlay

- [x] Create `overlays/prod/todo/application.yaml`
- [x] Create `overlays/prod/todo/values.yaml` with git repo config
- [x] Add to `overlays/prod/kustomization.yaml`

### Secrets

- [ ] SSH deploy key secret for git push

### Verification

- [x] `helm template todo charts/todo/ --namespace todo` renders correctly
- [ ] Deploy via ArgoCD
- [ ] Test public site loads
- [ ] Test admin UI behind Zero Trust
- [ ] Verify scheduler triggers at midnight PST
