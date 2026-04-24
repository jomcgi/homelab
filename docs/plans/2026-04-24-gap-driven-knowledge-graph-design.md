# Gap-Driven Knowledge Graph — Design

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

The shape is deliberately model-agnostic and storage-agnostic — any setup
that can track state per gap, run workers off that state, and enforce
structured contracts between stages will satisfy it.

## Outcome

A self-driving knowledge graph that uses unresolved Obsidian wikilinks as
the research agenda, grows trusted atoms automatically, and keeps expensive
model use proportional to where judgement actually matters.

## Features

- Gap-driven ingest: the vault tells the system what to research next
- Cluster-level briefing: related gaps researched together, not in isolation
- Asymmetric model use: small judgement calls up front, bulk work on local
  compute, structured verification in the middle
- Provenance on every atom: which model, which prompt version, which source,
  which confidence
- Trust as a first-class query dimension, not a binary accept/reject
- Rejection is preserved, not deleted — history is queryable
- Feedback from downstream quality back to upstream briefing
- Full observability: one trace per term, from unresolved link to committed
  atom

## Requirements

### Data

- Unexplored gaps tracked with their surrounding context, not just the term
- Embeddings on gaps so related ones can be grouped
- Clear state for each gap through the pipeline (discovered → researched →
  verified → consolidated → committed/rejected)
- Stable cluster assignments once made, to avoid briefs churning
- Provenance and pipeline version stamped on every atom for retroactive
  re-scoring

### Processing

- Deterministic span verification before any model review (cheapest
  hallucination filter)
- Structured output contracts at every model boundary — no prose between
  stages
- Batch processing at the cluster level to amortise briefing cost and catch
  within-batch duplicates
- Stateless, resumable workers driven off the gap's current state
- Idempotent discovery so re-scanning the vault is safe

### Judgement boundaries

- High-capability model: disambiguation, scope-setting, connection hints,
  rejection criteria
- Mid-capability model: structured verification, deduplication, consolidation
- Local model: bulk extraction against a tight directive
- Deterministic code: anything that doesn't need judgement

### Feedback

- Per-brief rejection rates surfaced back to briefing stage
- Per-source-domain quality scores to auto-demote bad sources
- Delay the feedback loop until there's enough data to avoid tuning on noise

### Operational

- Vault stays human-authored; machine output lives in the graph, not as new
  notes
- Pipeline version on every atom so prompt changes don't silently corrupt
  trust scores
- Graph-level metrics (atoms/day, rejection rate per stage, trust
  distribution) as the health signal

## Out of scope for this document

- Concrete schema (gap table columns, cluster identifiers, atom provenance
  fields)
- Worker topology (separate scheduler jobs vs. a single DAG runner)
- Model choices (which specific models fill which judgement tier)
- Storage choices (Postgres-only vs. separate queue vs. object store for
  briefs)
- UI surface in `kg-explorer` for reviewing rejections or trust

Those belong in a follow-up implementation plan, which can take this
requirements spec as its contract.
