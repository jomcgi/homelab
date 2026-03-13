# New Agent Recipes Design

**Date:** 2026-03-13
**Status:** Approved

## Goal

Add 6 new goose agent recipes to the orchestrator and update deep-plan's
prompt with composition patterns so it can design pipelines using them.

## Decisions

- **No rigid JSON output contracts** — LLMs pass context via prose + goose-result blocks.
  The orchestrator's `buildStepContext()` handles inter-step communication.
- **Split research** — existing `research` stays infra-focused; new `web-research` handles
  general-purpose topics with external sources.
- **Opus for critical thinking** — `critic` and `adr-writer` get `model: claude-opus-4-6`
  since they make judgment calls. Other new agents use the default Sonnet model.
- **Deep-plan gets composition hints** — new `## Composition Patterns` section with
  common DAG shapes. Fast-infer (`pipeline-config.js`) auto-discovers agents from API.
- **All recipes validated by CI** — `recipe_validate_test.go` embeds `recipes/*.yaml`
  and checks fields, template vars, goose-result blocks, and indent filters.

## New Recipes

### 1. `web-research` (analyse)

General-purpose web research on any topic. Cross-references multiple sources,
produces a structured gist. Full extensions (developer, context-forge, github).

- Icon: `🌐` | bg: `#e0e7ff` | fg: `#3730a3`
- Output: `gist | issue`
- max_turns: 30

### 2. `critic` (validate)

Reviews upstream agent output for gaps, errors, unverified claims. Has full
extensions to fact-check against cluster/repo state. Uses Opus for judgment quality.

- Icon: `⚖` | bg: `#fef9c3` | fg: `#854d0e`
- Output: `gist`
- max_turns: 15
- model: claude-opus-4-6

### 3. `trip-planner` (action)

Plans trips with day-by-day itineraries, logistics, open questions. No context-forge
(no cluster relevance). Developer + github only.

- Icon: `🗺` | bg: `#ccfbf1` | fg: `#134e4a`
- Output: `gist`
- max_turns: 40

### 4. `idea-capture` (action)

Captures freeform brain dumps as structured markdown in `docs/ideas/`. Creates PRs.
No questions asked — works with what it has.

- Icon: `💡` | bg: `#fce7f3` | fg: `#831843`
- Output: `pr`
- max_turns: 10

### 5. `claude-config` (action)

Improves Claude Code configuration (CLAUDE.md, settings.json, skills). Reads current
state, fetches Anthropic docs, opens a PR. Full extensions.

- Icon: `🛠` | bg: `#f3e8ff` | fg: `#6b21a8`
- Output: `pr`
- max_turns: 30

### 6. `adr-writer` (action)

Authors Architecture Decision Records. Reads existing ADRs, inspects cluster/repo
state, gates on whether a decision warrants an ADR. Uses Opus. Full extensions.

- Icon: `📋` | bg: `#dbeafe` | fg: `#1e3a8a`
- Output: `pr | issue`
- max_turns: 20
- model: claude-opus-4-6

## Modifications to Existing Recipes

### `docs` recipe

Remove ADR references. Scope to: VitePress docs site, READMEs, service documentation.

### `deep-plan` recipe

Add new agents to `## Available Agents` list. Add `## Composition Patterns`:

```
- research → critic: Validated infrastructure findings
- web-research → critic: Validated external research
- web-research → trip-planner: Travel planning with pre-research
- code-fix → critic → pr-review: Reviewed, validated fixes
- feature → qa-test → pr-review: Feature with test coverage and review
- web-research → adr-writer: Research-backed architecture decisions
- research → code-fix → critic: Investigate, fix, validate
```

## Files to Create/Modify

**New files (recipes/):**

- `web-research.yaml`
- `critic.yaml`
- `trip-planner.yaml`
- `idea-capture.yaml`
- `claude-config.yaml`
- `adr-writer.yaml`

**Modified files:**

- `recipes/docs.yaml` — remove ADR references
- `recipes/deep-plan.yaml` — add agents + composition patterns
- `chart/values.yaml` — add 6 agent entries + update docs entry
