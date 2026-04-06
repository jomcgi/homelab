# Build Changelog Notifier

## Problem

No visibility into what's shipping to the homelab cluster. Commits land on main but there's no notification to Discord summarizing what changed.

## Solution

An hourly changelog notifier that runs inside the monolith's chat module. It polls GitHub for new commits on main, filters to `feat`/`fix` conventional commit types (ignoring tests, style, chores), sends them to Gemma for concise human-readable summaries, and posts a rich Discord embed to a configured channel. Also includes CI status of the last completed check suite.

## Architecture

```
monolith (chat module)
  changelog.py
  ├─ _changelog_loop()          ← asyncio background task
  │   ├─ sleep until next :00   ← cron-aligned, not relative
  │   ├─ GET /repos/.../commits (since last_polled_sha)
  │   ├─ filter to feat/fix conventional commits
  │   ├─ GET /repos/.../check-suites (main HEAD)
  │   │   └─ skip in_progress, use last completed
  │   ├─ POST to Gemma (summarize changes)
  │   └─ bot.get_channel().send(embed)
  │
  └─ State: last_polled_sha (in-memory, seeded from HEAD on startup)
```

## Key Decisions

- **Cron-aligned schedule**: Sleeps until the next hour boundary (e.g. 14:00, 15:00), not `sleep(3600)` from whenever the pod started.
- **In-memory state**: Tracks `last_polled_sha` — on pod restart, seeds from current HEAD so it doesn't replay old history. No database needed.
- **Gemma summarization**: Passes commit type, message, and files changed to Gemma. Asks for a 1-2 sentence explanation per change, grouped by features vs fixes.
- **CI status**: Queries GitHub check suites for HEAD of main. Skips any `in_progress` suites and reports the conclusion of the last `completed` suite.
- **Silent when empty**: No Discord message if there are no feat/fix commits in the polling window.
- **No retry queue**: If a Discord send fails, log and try next hour.

## Files Changed

| File                                                | Change                                                           |
| --------------------------------------------------- | ---------------------------------------------------------------- |
| `projects/monolith/chat/changelog.py`               | New — GitHub polling, Gemma summarization, Discord embed posting |
| `projects/monolith/app/main.py`                     | Wire `changelog_loop` as a new `asyncio.create_task` in lifespan |
| `projects/monolith/chart/templates/deployment.yaml` | Add `GITHUB_TOKEN` env var from chat-secrets                     |
| `projects/monolith/deploy/values.yaml`              | Add `chat.githubRepo` and `chat.changelogChannelId` config       |

## Out of Scope

- Database persistence for polling state
- BuildBuddy webhook integration (GitHub polling is simpler)
- Backfill on startup
- Retry queue for failed Discord sends
