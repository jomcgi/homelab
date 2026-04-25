# knowledge_research

Opus 4.7 prompts and wrappers for researching gaps in Joe's Obsidian
vault. A local complement to the in-cluster `knowledge.research-gaps`
scheduled job — useful when:

- The cluster's Qwen-driven pipeline is backlogged and you want to drain
  some of the queue from a Mac with weekly-token headroom.
- The gap is `internal` / `personal` (Joe's own thinking) and needs a
  conversational extraction rather than a web-research pass.

## Architecture

Both flows are **two-phase** to maximize output quality:

1. **Phase 1 — Explore the local neighborhood.** The parent claude
   session reads the stub, walks `referenced_by` edges, finds adjacent
   clusters via grep + tag overlap, and produces a research brief
   summarizing Joe's existing coverage and the precise gap.
2. **Phase 2 — Do the focused work.**
   - **External flow** dispatches a subagent (`Task` tool,
     `subagent_type: general-purpose`) with the Phase 1 brief. The
     subagent does the open-web research and returns structured findings.
     This keeps the parent's context clean and gives the web research a
     tight, cluster-aware framing.
   - **Internal flow** opens a conversation with Joe instead, using the
     Phase 1 hypothesis to ask a single focused question rather than a
     blank "what do you mean by X". No subagent — the conversation is
     the value-add.

Then the parent synthesizes Phase-1 vault findings + Phase-2 output into
the final note.

## Two-step write flow

The vault has a Phase-A ingest job that periodically scans `<vault>/*.md`
and moves found files into `_raw/`. To avoid that job racing in-progress
edits, both flows write into a **staging directory** first and the
wrapper script atomically promotes the file to vault root once the
session is complete.

```
<vault>/.opus-research/<slug>.md   ← claude writes here (Phase A skips, dot-prefixed)
                ↓ atomic mv on clean exit
<vault>/<slug>.md                  ← Phase A picks up here, normal ingest happens
                ↓ Phase A
<vault>/_raw/YYYY/MM/DD/<hash>.md
                ↓ gardener
<vault>/_processed/<atom>.md
                ↓ reconciler
gap stub in _researching/ resolved
```

The dot-prefix is auto-excluded by `_discover_vault_root_drops()` and
hidden by Obsidian — no pipeline changes needed.

## Layout

```
tools/knowledge_research/
├── prompts/
│   ├── research-external.system.md   # web + vault research, non-interactive
│   └── research-internal.system.md   # conversational, asks Joe directly
├── bin/
│   ├── research-gap.sh               # batch external research
│   └── research-gap-interactive.sh   # one-at-a-time interactive
└── README.md
```

## Setup

1. Install the `claude` CLI (already done if you're reading this).
2. Set `VAULT` once in your shell rc:
   ```bash
   export VAULT="$HOME/Documents/Obsidian/<vault>"
   ```
3. Add the bin dir to PATH so the wrappers are globally callable:
   ```bash
   export PATH="$HOME/repos/homelab/tools/knowledge_research/bin:$PATH"
   ```
   Or symlink: `ln -s ~/repos/homelab/tools/knowledge_research/bin/* ~/bin/`.

The wrappers resolve their prompt files relative to their own location,
so they work from any cwd as long as the `tools/knowledge_research/`
checkout is intact.

## Usage

### Batch external research

Pulls `_researching/*.md` stubs with `gap_class: external`, runs Opus to
research each, stages the output at `<vault>/.opus-research/<slug>.md`,
and promotes it to `<vault>/<slug>.md` after each session. Resumable —
re-runs skip stubs that already have a staged or promoted file.

```bash
research-gap.sh                      # default: up to 50 stubs
research-gap.sh --max 10
research-gap.sh --filter '^ddd-'     # regex over slug
research-gap.sh --vault ~/path/to/vault --max 5
```

Each stub costs roughly 5-15K input tokens and 3-5K output. On Max-20×
that's ~0.3-0.5% of the weekly all-models limit per stub.

### Interactive personal research

Drops into a conversational `claude` session for a single internal/
personal gap. Opus opens with a synthesis of what it's already read from
`referenced_by`, asks one focused question, and after 3-5 turns drafts a
note for your review in `.opus-research/<slug>.md`. On approval you
exit the session and the wrapper promotes the file.

```bash
research-gap-interactive.sh ruinous-empathy-trap   # by slug
research-gap-interactive.sh --pick                 # fzf picker over eligible
research-gap-interactive.sh --no-promote <slug>    # leave staged for inspection
```

The picker requires `fzf` (`brew install fzf`).

The interactive flow caps itself at 5 questions and shows the draft
before exit. You can always say "no, change X" before approving.

## What lands in the vault

Both flows produce a markdown file at `<vault>/<slug>.md` with this shape:

```markdown
---
title: <Title>
tags: [<lowercase-kebab-tags>]
source: opus-research # or opus-interactive
researched_at: 2026-04-25T16:30:00Z
references:
  - <note_id_1>
  - <note_id_2>
---

# <Title>

<3-5 sentence framing>

## Key claims

- <claim 1>
- <claim 2>

## Why it matters in this vault # external flow

## Joe's framing # interactive flow

<...>

## Sources

- [[<note_id>]] — <what was used>
- <https://...> — <what was used> # external only
```

The vault's existing pipeline owns everything after promotion — move to
`_raw/`, atomize claims, populate `_processed/`, reconcile the gap stub,
eventually consolidate near-duplicates. We don't reach inside those
stages.

## Hard guarantees

- **Idempotent.** Re-running on stubs that already have output (staged or
  promoted) is a no-op.
- **No silent overwrite.** Both prompts refuse if the target file already
  exists; the user must explicitly confirm.
- **No race with Phase A.** Files in `.opus-research/` are invisible to
  the ingest scanner until promotion.
- **No invented citations.** Sources are mechanically tied to actual tool
  calls — every `[[note_id]]` was Read, every URL was WebFetched.
- **No vault writes outside `<vault>/<slug>.md` and `.opus-research/`.**
  Stubs in `_researching/` are not touched directly; the reconciler
  resolves them after atomization.
- **Abort-safe.** If you Ctrl-C an interactive session or claude crashes,
  the staged file is left in `.opus-research/` for inspection. No
  partial promotions.
