# External Research Pipeline — Design

## Changelog

- initial: design captured from brainstorming session covering architecture,
  components, data flow per cycle, error handling, and testing strategy

## Context

The gap-driven knowledge graph design
(`docs/plans/2026-04-24-gap-driven-knowledge-graph-design.md`) calls for a
self-driving graph that turns unresolved Obsidian wikilinks into a research
agenda, grows trusted atoms automatically, and keeps expensive model use
proportional to where judgement actually matters.

Slice #1 (PR #2193 + the `0.53.x` hotfix series) shipped the front of that
pipeline: discovery, classification, stub notes in `_researching/`, and the
review queue for `internal` gaps. After classification, an `external` gap
currently has no terminal — it sits at `state='classified'` indefinitely.

This design specifies slice #2: an external research pipeline that takes
`external+classified` gap stubs through a three-tier model spine and lands
validated research notes in `_inbox/research/`, where the existing
`raw_ingest → reconciler → gardener` pipeline produces atoms with proper
provenance.

The hybrid path, cluster-scoped briefing, domain reputation, and feedback
loops from the parent design doc are deferred to subsequent slices.

## Outcome

External gaps drain end-to-end. The pipeline:

- Pulls `external+classified` gaps in batches of 3 every 5 minutes
- Runs a Pydantic AI agent on local Qwen with three retrieval tools
  (`search_knowledge`, `web_search` via SearXNG, `web_fetch`)
- Produces a `ResearchNote(summary, claims)` with sources mechanically
  derived from the harness's tool-call audit trail
- Validates each claim with Sonnet (per-claim verdicts: supported,
  unsupported, speculative)
- Lands validated notes as `type: research` raws in `_inbox/research/`,
  carrying full provenance frontmatter (Qwen model, Sonnet model,
  pipeline version, fetched URLs with content hashes)
- Quarantines fully-rejected drafts to `_failed_research/<slug>-<N>.md`
  for diagnostics
- Parks gaps after 3 consecutive validation failures
- Lets the existing gardener decompose research raws into atoms,
  projecting `source_tier` onto each atom based on how many web sources
  the original research consulted

## Architecture

```
external+classified gap stub (_researching/<slug>.md)
     │
     ▼
[Qwen agent loop, Pydantic AI on llama.cpp]
     ├── tools: search_knowledge | web_search (SearXNG) | web_fetch
     └── output: ResearchNote(summary, claims) + harness-derived sources bundle
     │
     ▼
[Sonnet validator, claude CLI subprocess]
     └── output: per-claim verdicts (supported | unsupported | speculative)
     │
     ▼
all-unsupported? ──yes──▶ quarantine to _failed_research/<slug>-<N>.md
     │                     research_attempts++
     │                     (>=3 → gap.state = parked)
     no
     │
     ▼
write supported claims as type:research raw to _inbox/research/<slug>.md
gap.state = committed
     │
     ▼
[existing pipeline, untouched]
raw_ingest.move_phase → reconciler → gardener decomposes → atoms in _processed/atom/
                                                          (source_tier projected from sources)
```

State machine for slice #2 gaps:

```
discovered ──[classifier]──▶ classified
                                  │
                                  │ [research-gaps tick: select 3]
                                  ▼
                              researching
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
        [Qwen/Sonnet         [Sonnet rejects        [Sonnet accepts
        infra error]         all claims]            ≥1 claim]
                │                 │                  │
                ▼                 ▼                  ▼
        revert→classified   research_attempts++   committed
        (next tick retry)   attempts >= 3?         (raw in _inbox/)
                            ┌───┴───┐
                            yes    no
                            │      │
                            ▼      ▼
                          parked  classified
                                  (next tick retry)
```

The asymmetric model spine ends up well-balanced: Qwen does retrieval-heavy
synthesis on local compute (cheap tool calls, large context window),
Sonnet does verification (Anthropic's verification quality is well-suited
to the per-claim task), and Claude (via the existing classifier and
gardener) does the high-cap routing/decomposition judgement. Each tier
earns its keep by doing what it is structurally best at.

The only new code is the **front half**. The back half — `raw_ingest`,
reconciler, gardener, `AtomRawProvenance` — is unchanged. Research notes
become normal vault raws once they land in `_inbox/research/`,
indistinguishable from hand-authored raws in every downstream stage.

## Components

### New modules in `projects/monolith/knowledge/`

| Module                  | Responsibility                                                                                                                                                                                                                                                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `research_agent.py`     | Pydantic AI agent setup. Defines `ResearchDeps`, `Claim`, `ResearchNote(summary, claims)` output type. Factory `create_research_agent()` registers three tools and binds Qwen via `OpenAIChatModel`. Mirrors `chat/agent.py` (no shared harness yet — duplication tolerated until a third caller appears).   |
| `research_tools.py`     | Three Pydantic AI tool functions. `search_knowledge(query)` queries the existing knowledge KG; `web_search(query)` re-exports `chat.web_search.search_web` (SearXNG); `web_fetch(url)` is a new httpx-based page-body fetcher with timeout, content-type filter, and max-bytes cap.                          |
| `research_validator.py` | Sonnet-driven per-claim verifier using the `claude` CLI subprocess pattern (matches `gap_classifier.py`, keeps Claude Max ToS compliance). Spawns `claude --model sonnet --print -p <prompt>`, parses JSON stdout into `ValidatedResearch(claims=[ValidatedClaim(text, verdict, reason)])`.                  |
| `research_writer.py`    | Success path: `write_research_raw(vault_root, slug, supported_claims, sources)` → `_inbox/research/<slug>.md` with `type: research` and full provenance frontmatter. Failure path: `quarantine(vault_root, slug, attempt, draft, sonnet_reasons)` → `_failed_research/<slug>-<N>.md`.                        |
| `research_handler.py`   | The scheduled-job entry point: `research_gaps_handler(session)`. Per tick selects 3 `external+classified` gaps; for each, marks `researching`, runs agent, validates, branches on verdict, writes file, transitions state. Idempotent on partial failure. Mirrors `classify_gaps_handler` from `service.py`. |

### Modifications to existing files

- **`models.py`** — add `Gap.research_attempts: int = 0`. State column stays
  text; add `'researching'`, `'committed'`, `'parked'` to wherever state
  values are validated.
- **`service.py`** — register the scheduled job:
  `register_job(session, name="knowledge.research-gaps",
interval_secs=300, ttl_secs=600, handler=research_gaps_handler)`.
- **`raw_ingest.py:_infer_source`** — recognize the `"research"`
  subdirectory prefix and stamp `source='research'` on the `RawInput`.
- **`gardener.py`** — when decomposing a raw with `type: research`,
  project `source_tier` onto each output atom based on the raw's
  `sources` list.

### Schema migration

`projects/monolith/chart/migrations/<timestamp>_knowledge_gaps_research_state.sql`:
`ALTER TABLE knowledge.gaps ADD COLUMN research_attempts INTEGER NOT NULL DEFAULT 0`.

## Data flow per cycle

Every 5 min, `knowledge.research-gaps` runs one tick:

```
1. SELECT 3 gaps WHERE gap_class = 'external' AND state = 'classified'
   ORDER BY created_at LIMIT 3.

2. For each gap (sequential):
   a. Lock: UPDATE gaps SET state='researching' WHERE id=:id
            AND state='classified'.
      (0 rows updated → race lost, skip silently.)

   b. Build context from gap stub: term, referenced_by, source-note titles.
      Run Pydantic AI agent with output_type=ResearchNote.
      Tools available: search_knowledge, web_search, web_fetch.
      Capture RunContext.message_history → derive sources_bundle
      mechanically (every web_fetch URL with content hash, every
      web_search query with result URLs, every search_knowledge query
      with returned note IDs).

   c. Spawn `claude --model sonnet -p <validator_prompt>` with note +
      sources. Parse JSON stdout into ValidatedResearch.

   d. Branch on verdicts:
      - Qwen or Sonnet infra error → revert state to 'classified',
        do not bump research_attempts. Log + emit metric.
      - All claims unsupported       → write _failed_research/<slug>-<N>.md;
                                       research_attempts++; if ≥ 3,
                                       state='parked' else 'classified'.
      - At least one supported claim → filter to supported subset; write
                                       _inbox/research/<slug>.md;
                                       state='committed'.

3. Emit SigNoz metrics: gaps_processed, gaps_committed, gaps_parked,
   claims_supported_total, claims_dropped_total, validation_failures,
   infra_failures.
```

### Frontmatter of `_inbox/research/<slug>.md`

```yaml
---
type: research
id: <slug>
title: "Research note: <gap.term>"
derived_from_gap: <slug>
qwen_model: qwen3.6-27b
sonnet_model: sonnet-4-6
validator_version: sonnet-4-6@v1
pipeline_version: research-pipeline@v1
researched_at: 2026-04-25T10:00:00Z
sources:
  - tool: web_fetch
    url: "https://example.com/foo"
    content_hash: "sha256:abc123..."
    fetched_at: "2026-04-25T09:55:12Z"
  - tool: search_knowledge
    query: "what is X"
    note_ids: ["my-prior-note-on-x"]
  - tool: web_search
    query: "X explained"
    result_urls: ["https://blog1.com/x"]
claims_supported: 4
claims_dropped: 1
---

## Summary

<Qwen's summary>

## Supported claims

- <Claim 1 text> _[evidence: web_fetch:https://example.com/foo]_
- <Claim 2 text> _[evidence: search_knowledge:my-prior-note-on-x]_

## Sources

<bulleted URLs + titles>
```

### Frontmatter of `_failed_research/<slug>-<N>.md`

```yaml
---
type: failed_research
id: <slug>-<attempt>
derived_from_gap: <slug>
attempt: <N>
qwen_model: qwen3.6-27b
sonnet_model: sonnet-4-6
researched_at: 2026-04-25T10:00:00Z
sonnet_reasons:
  - claim: <text>
    verdict: unsupported
    reason: "no source cited"
  - claim: <text>
    verdict: speculative
    reason: "hedged language not backed by evidence"
sources_attempted: [...]
---
# Failed research draft (Qwen output)

<Qwen's summary and full claims, preserved for diagnostics>
```

### Atom `source_tier` projection (gardener-side)

Counting `web_fetch` entries in the raw's `sources` frontmatter:

- 0 web_fetch → atom `source_tier: personal` (vault-grounded only)
- 1 web_fetch → atom `source_tier: direct` (single primary source)
- 2+ web_fetch → atom `source_tier: research` (cross-source synthesis)

This is the only gardener-side change required. All other gardener
behavior (Claude decomposition, atom file creation, AtomRawProvenance
linkage) is unchanged.

## Error handling

| Failure                                            | State on exit            | `research_attempts` | Effect                                                               |
| -------------------------------------------------- | ------------------------ | ------------------- | -------------------------------------------------------------------- |
| Qwen endpoint down (llama.cpp unreachable)         | `classified`             | unchanged           | Retry next tick. Infrastructure issue; SigNoz alert at >5min outage. |
| Sonnet CLI error (subprocess failure, JSON parse)  | `classified`             | unchanged           | Retry next tick. Same category as Qwen — not the gap's fault.        |
| Sonnet rejects all claims                          | `classified` or `parked` | +1                  | If `attempts >= 3` → `parked`. Quarantine file written either way.   |
| Vault FS error (write to `_inbox/research/` fails) | `classified`             | unchanged           | Retry next tick. Log error.                                          |
| Race lost (gap state changed under us)             | unchanged                | unchanged           | Skip silently.                                                       |
| Qwen returns `claims=[]`                           | `classified` or `parked` | +1                  | Treated as "all unsupported."                                        |

The key invariant: **infrastructure failures don't burn attempts**, only
gap-specific quality failures do. This prevents a flaky llama.cpp window
from auto-parking every gap in the pipeline. It also gives `parked`
semantic weight: a parked gap means we genuinely tried 3 times with
working infrastructure and the model could not substantiate claims.

`derived_from_gap: <slug>` in the raw frontmatter is the only durable
backlink between an atom and the gap that produced it. Combined with
`AtomRawProvenance.derived_note_id` (which links atoms to raws), the
full trace `gap → raw → atom` is recoverable via two joins. No new
schema needed for trace-level observability — just SigNoz queries over
the existing tables.

## Testing strategy

Fully mocked LLM tier in CI; no live calls.

| Layer                   | Approach                                                                                                                                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `research_tools.py`     | `web_fetch` against httpx mock (success, timeout, non-200, content-type filter). `search_knowledge` against an in-memory fake KG. `web_search` already covered by existing chat tests.                  |
| `research_agent.py`     | Pydantic AI `FunctionModel` (already used in `chat/agent_*_test.py`) to drive a deterministic agent loop. Assert `sources_bundle` is reconstructed correctly from `message_history`.                    |
| `research_validator.py` | Monkeypatch `asyncio.create_subprocess_exec` to return canned JSON, malformed JSON, or non-zero exit. Mirrors `gap_classifier_test.py`.                                                                 |
| `research_writer.py`    | Golden tests for frontmatter shape (success + quarantine paths). Idempotency. Attempt-suffix increment. Byte-stability per existing `gap_stubs_test.py` precedent.                                      |
| `research_handler.py`   | End-to-end with all three mocked: classified → committed (happy path), classified → parked (3 failures), classified → classified (Qwen error doesn't bump). State-machine transitions are the contract. |
| Migration               | `research_attempts` column exists, default 0, backfilled on existing rows.                                                                                                                              |
| Gardener                | `type: research` raws decompose normally; `source_tier` projection (0/1/2+ web_fetch counts) tested on the gardener side.                                                                               |

First real validation happens when the chart bump rolls out via ArgoCD
and the scheduled job picks up the first batch from prod. SigNoz
dashboards (research-gaps cycle metrics, quarantine file counts by
attempt suffix) tell us if it is working without watching pods.

## Out of scope (deferred to subsequent slices)

- **Hybrid path** — `hybrid` gaps currently route nowhere. The natural
  follow-up is "external research produces a draft into the review queue
  for user annotation rather than auto-commit." Reuses this slice's
  Qwen+Sonnet pipeline; only the terminal write differs.
- **Cluster-scoped briefing** — embed gaps, cluster by similarity, brief
  per-cluster rather than per-gap. The throughput optimization once
  per-gap research is observed in production.
- **Domain reputation** — per-source-domain quality scores feeding back
  into briefing. Only meaningful once we have enough commits to score.
- **Per-brief rejection rate metrics → briefing feedback loop** — needs
  the cluster substrate first.
- **Atom consolidation via typed edges** — atoms today are individually
  committed; the design doc calls for additive consolidation (new atoms
  superseding via typed edges, never mutating committed atoms). Out of
  scope until the commit volume warrants it.
- **`hybrid_path_validator`** — Sonnet-driven decision to route ambiguous
  research to the review queue. Adjacent to the hybrid path above.
- **Shared Pydantic AI harness** — `chat/agent.py` and
  `knowledge/research_agent.py` will duplicate Pydantic AI plumbing.
  Acceptable until a third caller appears.
- **kg-explorer UI** — visualizing the gap → raw → atom trace. Trace data
  is recoverable from SigNoz today; UI work is out of scope.

These are the natural next slices once this PR ships and we observe
real distribution of `committed` vs `parked` gaps and atom source-tier
distribution.
