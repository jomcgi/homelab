# Recipe-Driven Agent Registry Design

**Date:** 2026-03-12
**Status:** Approved

## Problem

The pipeline composer UI needs to know which agents are available, with metadata (label, icon, colors, category) for display. Currently this requires maintaining a separate `agentsConfig` in Helm values that duplicates information already in the goose recipe files. Adding a new agent means updating both the recipe YAML and the Helm values — two sources of truth that can drift.

Additionally, goose recipes are baked into the goose-agent container image. This means adding or modifying a recipe requires rebuilding and redeploying the goose-agent image and its warm pool, even when only the recipe content changed.

## Decision

Move recipes into Helm values as the single source of truth. The orchestrator manages recipes as data, sends them to runners over HTTP at dispatch time, and serves UI metadata to the frontend.

## Design

### Recipe Format in Helm Values

Each agent entry in `agentsConfig.agents[]` contains both UI metadata and the full goose recipe:

```yaml
agentsConfig:
  agents:
    - id: ci-debug
      label: CI Debug
      icon: "..."
      bg: "#dbeafe"
      fg: "#1e40af"
      desc: Analyse CI/build failures using BuildBuddy logs
      category: analyse # analyse | action | validate | tool
      recipe:
        version: "1.0.0"
        title: CI Debug
        description: Debug CI build failures
        instructions: |
          You are debugging a CI build failure...
        prompt: |
          {{ task_description }}
        parameters:
          - key: task_description
            input_type: string
            requirement: required
        extensions:
          - type: builtin
            name: developer
        settings:
          max_turns: 50
```

External umbrella chart consumers add agents by adding entries to this list in their values override.

### Agent Categories

Agents are grouped by intent for the pipeline composer UI:

| Category   | Intent                           | Examples                       |
| ---------- | -------------------------------- | ------------------------------ |
| `analyse`  | Collect data, research, diagnose | CI debug, research             |
| `action`   | Fix, implement, deploy           | Code fix, bazel                |
| `validate` | Review, test, verify             | PR review, test writer         |
| `tool`     | Run specific tool, notify        | Slack notifier, webhook poster |

### ConfigMap Mount

The `agentsConfig` is rendered as a JSON ConfigMap and mounted into the orchestrator at `/etc/orchestrator/agents.json`. A checksum annotation triggers pod restarts on config changes.

### Orchestrator Startup

`loadAgentsConfig` reads the mounted JSON file and splits each agent into:

- **UI metadata** (id, label, icon, bg, fg, desc, category) — served via `GET /agents`
- **Recipe content** (the `recipe` field) — stored in `map[string]AgentRecipe`, used at dispatch

### Job Dispatch Flow

```
1. User builds pipeline in composer UI (using agent IDs from GET /agents)
2. Orchestrator receives pipeline submission
3. For each step, orchestrator:
   a. Looks up agent ID in recipes map
   b. Renders template (substitutes {{ task_description }})
   c. Marshals recipe to YAML string
   d. Sends {task, recipe: "<rendered YAML>"} to runner via POST /run
4. Runner writes recipe to temp file, runs: goose run --recipe /tmp/recipe.yaml
```

### Template Rendering

Recipes use `{{ task_description }}` and `{{ task_description | indent(N) }}`. The orchestrator handles these two patterns with simple string replacement — no Jinja engine needed.

### Runner Changes

`RunRequest` changes from `{task, profile}` to `{task, recipe}`:

- If `recipe` is set: write to temp file, run `goose run --recipe <path> --no-profile`
- If empty: run `goose run --text <task>` (bare mode)

Removed from runner: `discoverProfiles()`, `validProfiles`, `recipesDir`.

### Orchestrator Removals

- `ValidProfiles` map in `model.go`
- `GET /profiles` endpoint (replaced by `GET /agents`)
- `TestValidProfilesMatchRecipeFiles` (no longer two sources to sync)

### Goose-Agent Image Changes

Recipe files are no longer baked into the image via `recipes_tar`. The image becomes a generic goose runtime. Recipe files remain in the repo as development reference.

### Extensibility

External chart consumers configure agents entirely through `values.yaml` overrides — no repo files, Bazel build steps, or image rebuilds required. The orchestrator reads whatever is in the mounted ConfigMap.
