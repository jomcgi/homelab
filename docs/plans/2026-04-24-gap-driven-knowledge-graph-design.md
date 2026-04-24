# Gap-Driven Knowledge Graph — Design

## Changelog

- initial: requirements spec split across outcome / features / requirements
  / out-of-scope
- review pass: brief scope made cluster-level explicit, domain-reputation
  called out as its own substrate, gap triage added, trust computation
  deferred
- personal-gaps extension: second gap class (user-resolvable), Opus-driven
  classification stage, review queue, hybrid path, Privacy subsection;
  trust model committed as immutable source tiers (`personal` / `direct` /
  `research`) with domain reputation affecting briefing only; consolidation
  clarified as additive

## Context

The current gardener (`projects/monolith/knowledge/gardener.py`, design:
`2026-04-08-knowledge-gardener-design.md`) is push-driven — it decomposes
raw notes that have already landed in the vault. Unresolved `[[wikilinks]]`
are rendered by `wikilinks.py` but never become work items; the graph has
no mechanism for turning its own gaps into a research agenda.

This design reframes the pipeline: the vault's unresolved wikilinks *are*
the agenda. The system researches gaps, grows trusted atoms automatically,
and keeps expensive model use proportional to where judgement actually
matters.

The vault also contains deeply personal notes. Some unresolved wikilinks
refer to the user's own thoughts, shorthand, relationships, or background
that cannot be found online. Routing these to external research produces
garbage atoms and leaks private context into search queries. They need a
different terminal path: surface the gap to the user, capture the answer,
land it as an atom with human provenance.

The shape is deliberately model-agnostic and storage-agnostic — any setup
that can track state per gap, run workers off that state, and enforce
structured contracts between stages will satisfy it.

## Outcome

A self-driving knowledge graph that uses unresolved Obsidian wikilinks as
the research agenda, grows trusted atoms automatically, and keeps expensive
model use proportional to where judgement actually matters.

The graph accommodates both externally-researchable gaps and gaps that
only the user can resolve, treating both as first-class with consistent
provenance and queryability.

## Features

- Gap-driven ingest: the vault tells the system what to research next
- Cluster-level briefing: related gaps researched together, not in isolation
- Asymmetric model use: small judgement calls up front, bulk work on local
  compute, structured verification in the middle
- Provenance on every atom: which model, which prompt version, which source,
  which tier
- Trust as a first-class query dimension via source tiers, not a binary
  accept/reject
- Two classes of gap: externally researchable vs. resolvable only by the
  user
- Classification stage that routes gaps by class before briefing
- Durable review queue for user-resolvable gaps, drainable at the user's
  pace
- Hybrid path: external research can produce a draft that lands in the
  review queue for user annotation rather than direct commit
- Privacy-conservative default: when classification is uncertain, route to
  the user rather than the web
- Rejection is preserved, not deleted — history is queryable
- Consolidation is additive — new facts produce new atoms that supersede
  or refine existing ones via typed edges; committed atoms are never
  mutated in place
- Feedback from downstream quality back to upstream briefing
- Full observability: one trace per term, from unresolved link to committed
  atom

## Requirements

### Data

- Unexplored gaps tracked with their surrounding context, not just the term
- Embeddings on gaps so related ones can be grouped
- Gap class recorded on the gap itself (`external` | `internal` | `hybrid`
  | `parked`)
- Explicit user-provided classification signals supported (e.g. marker
  convention on wikilinks, frontmatter flag on the source note) to override
  the classifier
- Clear state for each gap through the pipeline (discovered → classified
  → researched → verified → consolidated → committed/rejected; internal
  gaps skip research and sit in the review queue between classified and
  consolidated)
- Briefs are cluster-scoped, not gap-scoped — a gap carries its own state,
  a brief lives on the cluster the gap was assigned to; the "researched"
  state on a gap is satisfied by its cluster's brief
- Stable cluster assignments once made, to avoid briefs churning
- Review queue state tracked per gap so drain order and status are durable
- Provenance and pipeline version stamped on every atom for retroactive
  re-scoring
- Every atom carries a source tier, set at commit and immutable:
  - `personal` — user-answered from the review queue
  - `direct` — attributed to a single primary source (blog, transcript,
    paper, etc.)
  - `research` — synthesized across multiple sources by the pipeline
- Domain-reputation is its own state substrate — per-source-domain quality
  scores are not a view over atoms, they persist independently and feed
  back into briefing

### Processing

- Deterministic span verification before any model review (cheapest
  hallucination filter)
- Structured output contracts at every model boundary — no prose between
  stages
- Batch processing at the cluster level to amortise briefing cost and catch
  within-batch duplicates
- Classification runs after discovery and before briefing; it routes each
  gap to one of `external` / `internal` / `hybrid` / `parked`
- Classification is a judgement call, not a heuristic — misrouting is
  expensive in both directions (wasted tokens, wasted user time, privacy
  incidents); parked gaps stay queryable but don't consume budget until
  promoted
- Hybrid gaps route through external research first, then land in the
  review queue as a draft for annotation rather than auto-commit
- User-answer capture uses the same structured output contract as any
  other source — answers produce `personal`-tier atoms with optional
  source attribution
- Consolidation never mutates committed atoms — supersession or refinement
  is expressed through new atoms and typed edges, so rescoring and audit
  stay tractable
- Stateless, resumable workers driven off the gap's current state
- Idempotent discovery so re-scanning the vault is safe

### Judgement boundaries

- High-capability model: classification, disambiguation, scope-setting,
  connection hints, rejection criteria
- Mid-capability model: structured verification, deduplication,
  consolidation
- Local model: bulk extraction against a tight directive
- User: terminal judgement for `internal` and `hybrid` gaps
- Deterministic code: anything that doesn't need judgement

### Privacy

- No gap leaves the system for external research without passing
  classification
- Classification errs toward user-routing under uncertainty
- Over-routing to the user is tolerated; over-routing to the web is
  treated as a defect

### Feedback

- Per-brief rejection rates surfaced back to briefing stage
- Per-source-domain quality scores auto-demote bad sources at briefing
  time — reputation affects which sources get researched, not the tier of
  atoms already committed
- Delay the feedback loop until there's enough data to avoid tuning on
  noise

### Operational

- Vault stays human-authored; machine output lives in the graph, not as
  new notes
- Pipeline version on every atom so prompt changes don't silently corrupt
  downstream queries, and retroactive re-scoring jobs can target a version
- Graph-level metrics (atoms/day, rejection rate per stage, tier
  distribution, review queue depth) as the health signal

## Out of scope for this document

- Concrete schema (gap table columns, cluster identifiers, atom provenance
  fields, domain-reputation store columns, review queue state columns)
- Classifier criteria — the rule-set that routes a gap to `external` /
  `internal` / `hybrid` / `parked`
- Marker convention syntax for explicit user-provided classification
  signals
- Classifier prompt design and calibration
- UX of the review queue (CLI, web, Obsidian plugin, etc.)
- Worker topology (separate scheduler jobs vs. a single DAG runner)
- Model choices (which specific models fill which judgement tier)
- Storage choices (Postgres-only vs. separate queue vs. object store for
  briefs)
- UI surface in `kg-explorer` for reviewing rejections or trust

Those belong in a follow-up implementation plan, which can take this
requirements spec as its contract.
