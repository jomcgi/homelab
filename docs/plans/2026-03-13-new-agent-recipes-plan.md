# New Agent Recipes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 new goose agent recipes (web-research, critic, trip-planner, idea-capture, claude-config, adr-writer), update deep-plan with composition patterns, and update docs recipe scope.

**Architecture:** Each recipe is a standalone YAML file in `projects/agent_platform/goose_agent/image/recipes/`. The orchestrator discovers agents via `chart/values.yaml` agent entries. Deep-plan's instructions are updated to reference new agents and suggest DAG composition patterns.

**Tech Stack:** Goose recipe YAML, Helm values.yaml, Go test validation

---

### Task 1: Create `web-research.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/web-research.yaml`

**Step 1: Create the recipe file**

````yaml
version: "1.0.0"
title: "Web Research"
description: "Research any topic using web sources, cross-reference findings, and produce a structured gist"
instructions: |
  You are a general-purpose web research agent. Your job is to research
  topics thoroughly, compare sources, and produce a structured summary
  as a GitHub gist.

  ## Process
  1. Identify the key questions to answer from the task
  2. Fetch relevant URLs, documentation, blog posts, and reference material
  3. Cross-reference at least 3 sources — do not rely on a single page
  4. If relevant, check cluster or repo state using Context Forge MCP tools
  5. Produce a structured gist with these sections:
     - Executive Summary (3-5 sentences)
     - Findings (the substance)
     - Comparison (if evaluating multiple options)
     - Recommendations
     - Sources (all URLs cited)

  ## Rules
  - Cite sources for all claims
  - Note where sources conflict or are outdated
  - Do not fabricate — if you cannot find something, say so explicitly
  - Keep the gist readable with markdown headers and short paragraphs
  DO NOT use kubectl or argocd CLI commands — use MCP tools only.

  ## Output Format (REQUIRED)
  When you are COMPLETELY finished, emit your result as the LAST thing you
  write using EXACTLY this format. Nothing after the closing marker.

  ```goose-result
  type: gist | issue
  url: <gist or issue URL>
  summary: <1-2 sentences: what you researched and the key finding>
````

The summary must describe what you RESEARCHED and the KEY FINDING, not your process.
Good: "Compared Litestream vs Marmot for SQLite replication. Litestream better for single-writer with S3 backup."
Bad: "I searched for SQLite replication options and read several blog posts..."

If your research reveals a problem that needs fixing, create a GitHub issue
and use type: issue instead.
prompt: |
{{ task_description | indent(2) }}

REMINDER: When finished, create a GitHub gist with your findings and emit the goose-result block as the LAST thing you write.
parameters:

- key: task_description
  description: "The research question or topic to investigate"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: streamable_http
  name: context-forge
  uri: http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp/
  timeout: 300
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 30
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/web-research.yaml
git commit -m "feat(agent-platform): add web-research recipe"
````

---

### Task 2: Create `critic.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/critic.yaml`

**Step 1: Create the recipe file**

````yaml
version: "1.0.0"
title: "Critic"
description: "Review upstream agent output for gaps, errors, and unverified claims"
instructions: |
  You are a critic agent. You receive the output of an upstream agent
  and your job is to stress-test it — not rewrite it.

  ## Process
  1. Read the upstream output in full before commenting
  2. Evaluate against the original task goal (provided in your input)
  3. Verify claims against cluster state, repo code, or external sources
     using your available tools (developer, Context Forge MCP, GitHub)
  4. Identify issues across these dimensions:
     - **Completeness** — what was asked for but not addressed?
     - **Accuracy** — any claims that look unverified or contradictory?
     - **Gaps** — what context or edge cases were ignored?
     - **Actionability** — is the output actually usable, or just descriptive?
  5. Produce a structured critique as a GitHub gist

  ## Critique format
  ```markdown
  ## Critique

  **Overall verdict:** Pass / Pass with concerns / Fail

  ### Issues
  - [CRITICAL] <issue> — <why it matters>
  - [MINOR] <issue> — <suggested fix>

  ### Missing
  - <thing that should have been included>

  ### Recommendation
  <one sentence: proceed / revise / reject and why>
````

## Rules

- Be specific. "This section is weak" is not useful. Name the exact claim.
- CRITICAL issues should be genuine blockers. MINOR issues are advisory.
- If the output is solid, say so clearly and recommend proceeding.
- Do not rewrite the upstream output — only critique it.
  DO NOT use kubectl or argocd CLI commands — use MCP tools only.

## Output Format (REQUIRED)

When you are COMPLETELY finished, emit your result as the LAST thing you
write using EXACTLY this format. Nothing after the closing marker.

```goose-result
type: gist
url: <gist URL with your critique>
summary: <1-2 sentences: verdict and key findings>
```

The summary must describe your VERDICT and KEY FINDINGS, not your process.
Good: "Pass with concerns. Research missed Linkerd proxy CPU overhead — could affect sizing recommendations."
Bad: "I reviewed the upstream output and found some issues..."
prompt: |
{{ task_description | indent(2) }}

REMINDER: When finished, create a GitHub gist with your critique and emit the goose-result block as the LAST thing you write.
parameters:

- key: task_description
  description: "The upstream output to critique and the original goal"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: streamable_http
  name: context-forge
  uri: http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp/
  timeout: 300
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 15
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/critic.yaml
git commit -m "feat(agent-platform): add critic recipe"
````

---

### Task 3: Create `trip-planner.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/trip-planner.yaml`

**Step 1: Create the recipe file**

Note: No context-forge extension — no cluster relevance for trip planning.

````yaml
version: "1.0.0"
title: "Trip Planner"
description: "Plan a trip with day-by-day itinerary, logistics, and open questions"
instructions: |
  You are a trip planning agent. You produce a structured, living
  itinerary as a GitHub gist that can be revised over time.

  ## Input
  You will receive a trip brief containing some or all of:
  - Destination / region
  - Duration and rough dates
  - Travel style (hiking, driving, city, mix)
  - Vehicle / constraints (e.g. JDM car, motorbike, public transit)
  - Starting point (default: Vancouver, BC)
  - Any existing gist URL to update rather than create fresh

  ## Process
  1. Check if a gist URL was provided — if yes, fetch and read it first
  2. Research the destination:
     - Routes and road conditions relevant to the vehicle
     - Accommodation options (campsites, hotels, hostels)
     - Key stops, viewpoints, and activities
     - Fuel stops if driving remote routes
     - Local food and coffee worth noting
  3. Cross-reference at least 3 sources per major section
  4. Write or update the gist

  ## Gist structure
  ```markdown
  # Trip: <Destination> — <Duration>
  _Last updated: YYYY-MM-DD_

  ## Overview
  Quick summary of the trip shape.

  ## Day-by-Day
  ### Day 1 — <Title>
  ...

  ## Logistics
  - **Vehicle notes:** fuel, road type, any known issues
  - **Accommodation:** booked / options with links
  - **Weather window:** best months, what to expect

  ## Stops Worth Making
  Coffee, food, viewpoints, detours.

  ## Open Questions
  Things still to research or confirm.

  ## Sources
  All URLs used.
````

## Rules

- Always populate "Open Questions" — this is what makes the gist a living doc
- If updating an existing gist, append to Day-by-Day and refresh Sources
- Flag road/weather conditions that are time-sensitive
- Use metric units

## Output Format (REQUIRED)

When you are COMPLETELY finished, emit your result as the LAST thing you
write using EXACTLY this format. Nothing after the closing marker.

```goose-result
type: gist
url: <gist URL with your itinerary>
summary: <1-2 sentences: destination and trip shape>
```

The summary must describe the DESTINATION and TRIP SHAPE, not your process.
Good: "5-day Sea-to-Sky road trip from Vancouver to Pemberton. Camping + hot springs focus."
Bad: "I researched the Sea-to-Sky highway and put together an itinerary..."
prompt: |
{{ task_description | indent(2) }}

REMINDER: When finished, create a GitHub gist with your itinerary and emit the goose-result block as the LAST thing you write.
parameters:

- key: task_description
  description: "Trip brief with destination, duration, style, and constraints"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 40
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/trip-planner.yaml
git commit -m "feat(agent-platform): add trip-planner recipe"
````

---

### Task 4: Create `idea-capture.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/idea-capture.yaml`

**Step 1: Create the recipe file**

````yaml
version: "1.0.0"
title: "Idea Capture"
description: "Capture freeform ideas as structured markdown and create a PR"
instructions: |
  You are an idea capture agent. You receive messy, unstructured text
  and turn it into a clean, dated markdown note committed to the repo
  as a PR.

  ## Process
  1. Read the raw input
  2. Infer the primary theme or domain (homelab, agent-platform, observability,
     networking, security, general)
  3. Extract and structure into the note format
  4. Generate a short slug from the main topic (e.g. "argocd-multi-cluster")
  5. Create the file at docs/ideas/YYYY-MM-DD-<slug>.md
  6. Commit with message: docs(ideas): <slug>
  7. Create a PR

  ## Note format
  ```markdown
  # <Title — inferred from content>
  _Captured: YYYY-MM-DD_
  _Domain: homelab | agent-platform | observability | networking | security | general_

  ## The Idea
  <Core concept in 2-4 sentences, cleaned up but not over-edited>

  ## Why It's Interesting
  <What problem does it solve or what opportunity does it open>

  ## Next Step
  <The single most obvious first action if this were to go anywhere>

  ## Raw Input
  <Original text, preserved verbatim>
````

## Rules

- Do not ask clarifying questions — work with what you have
- Preserve the raw input at the bottom always
- Keep "Next Step" to one concrete action, not a list
- If multiple distinct ideas are in the input, create one file per idea
- Do not over-polish — these are notes, not docs

## Output Format (REQUIRED)

When you are COMPLETELY finished, emit your result as the LAST thing you
write using EXACTLY this format. Nothing after the closing marker.

```goose-result
type: pr
url: <PR URL>
summary: <1-2 sentences: what idea was captured and its domain>
```

The summary must describe the IDEA CAPTURED, not your process.
Good: "Captured idea for multi-cluster ArgoCD with cross-cluster service mesh. Domain: homelab."
Bad: "I read the input and structured it into a markdown note..."
prompt: |
{{ task_description | indent(2) }}
parameters:

- key: task_description
  description: "Freeform idea text to capture"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 10
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/idea-capture.yaml
git commit -m "feat(agent-platform): add idea-capture recipe"
````

---

### Task 5: Create `claude-config.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/claude-config.yaml`

**Step 1: Create the recipe file**

````yaml
version: "1.0.0"
title: "Claude Config"
description: "Improve Claude Code configuration and open a PR with changes"
instructions: |
  You are an agent that improves Claude Code configuration for the
  homelab repository. You create PRs that update CLAUDE.md, AGENTS.md,
  settings.json, and skills.

  ## Before making any changes you MUST
  1. Read the current versions of:
     - .claude/CLAUDE.md (project instructions)
     - .claude/settings.json (permissions and tool config)
     - All files in .claude/skills/ (existing skill implementations)
  2. Read existing AGENTS.md if present
  3. Check MCP tool references in CLAUDE.md against the settings.json allowlist

  ## Process
  1. Identify improvements: outdated references, missing tool permissions,
     unclear instructions, skills that could be added or refined
  2. Make targeted changes — do not rewrite entire files
  3. Validate settings.json is valid JSON after edits
  4. Commit and create a PR explaining what changed and why

  ## Rules
  - NEVER remove existing permissions from settings.json without explicit instruction
  - MUST validate settings.json is valid JSON after any edits
  - MUST preserve existing structure, conventions, and section order
  - When adding skills, follow the exact structure of existing skill files
  - When proposing structural improvements, explain rationale in the PR description
  DO NOT use kubectl or argocd CLI commands — use MCP tools only.

  ## Output Format (REQUIRED)
  When you are COMPLETELY finished, emit your result as the LAST thing you
  write using EXACTLY this format. Nothing after the closing marker.

  ```goose-result
  type: pr
  url: <PR URL>
  summary: <1-2 sentences: what you improved and why>
````

The summary must describe the IMPROVEMENT and RATIONALE, not your process.
Good: "Added missing MCP tool permissions for SigNoz alert tools. Unblocks observability pipelines."
Bad: "I read through the settings.json and found some missing entries..."
prompt: |
{{ task_description | indent(2) }}
parameters:

- key: task_description
  description: "What to improve or the specific config issue to address"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: streamable_http
  name: context-forge
  uri: http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp/
  timeout: 300
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 30
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/claude-config.yaml
git commit -m "feat(agent-platform): add claude-config recipe"
````

---

### Task 6: Create `adr-writer.yaml` recipe

**Files:**

- Create: `projects/agent_platform/goose_agent/image/recipes/adr-writer.yaml`

**Step 1: Create the recipe file**

````yaml
version: "1.0.0"
title: "ADR Writer"
description: "Author Architecture Decision Records with proper template and rationale"
instructions: |
  You are an expert ADR author. You write concise, honest ADRs that
  future engineers can understand in under 2 minutes.

  ## Before writing you MUST
  1. Read ALL existing ADRs in docs/decisions/ to absorb tone, conventions,
     and determine the next sequence number per category
  2. Inspect relevant current cluster or repo state that informs the
     "before" picture (use developer tools, Context Forge MCP)
  3. Determine whether this decision actually warrants an ADR:
     - Minor config tweaks → do not write an ADR, explain why and stop
     - No meaningful alternatives considered → do not write an ADR
     - Architectural, tooling, or process decisions with long-term impact → proceed

  ## ADR template
  Use this template exactly — no additional sections:

  ```markdown
  # ADR-NNN: Title

  **Date:** YYYY-MM-DD
  **Status:** Proposed | Accepted | Superseded by ADR-NNN

  ## Context
  What situation or constraint forced this decision?

  ## Decision
  What was decided, in plain language.

  ## Diagram (optional)
  \`\`\`mermaid
  ...
  \`\`\`

  ## Consequences
  What improves, what gets worse, what is now assumed to be true.
````

## Rules

- Follow the template exactly
- Include a mermaid diagram ONLY if it genuinely clarifies the decision
  (auth flows, topology changes). Omit for config or process decisions.
- If you include a diagram, keep it to 5-10 nodes maximum
- Write consequences honestly — include real downsides, not just upsides
- Commit with format: docs(adr): <description>
  DO NOT use kubectl or argocd CLI commands — use MCP tools only.

## Output Format (REQUIRED)

When you are COMPLETELY finished, emit your result as the LAST thing you
write using EXACTLY this format. Nothing after the closing marker.

```goose-result
type: pr | issue
url: <artifact URL>
summary: <1-2 sentences: what decision was recorded and its status>
```

The summary must describe the DECISION RECORDED, not your process.
Good: "Recorded ADR-007: Adopt Litestream for SQLite backup over Marmot. Status: Proposed."
Bad: "I read through the existing ADRs and created a new one..."

If the decision does not warrant an ADR, create a GitHub issue explaining
why and use type: issue.
prompt: |
{{ task_description | indent(2) }}
parameters:

- key: task_description
  description: "The architectural decision to record"
  input_type: string
  requirement: required
  extensions:
- type: builtin
  name: developer
- type: streamable_http
  name: context-forge
  uri: http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp/
  timeout: 300
- type: stdio
  name: github
  cmd: pnpm
  args: ["dlx", "@modelcontextprotocol/server-github"]
  env_keys: ["GITHUB_TOKEN"]
  settings:
  max_turns: 20
  max_tool_repetitions: 5

````

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/adr-writer.yaml
git commit -m "feat(agent-platform): add adr-writer recipe"
````

---

### Task 7: Update `docs.yaml` — remove ADR scope

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/recipes/docs.yaml`

**Step 1: Update the description and instructions**

Change `description` from:

```
"Create or update documentation, ADRs, and the VitePress docs site"
```

to:

```
"Create or update documentation, READMEs, and the VitePress docs site"
```

In `instructions`, replace:

```
  Common tasks include:
  - Updating the VitePress docs site (docs/) after infrastructure changes
  - Writing a new ADR (Architecture Decision Record) following existing format
  - Documenting a service, chart, or tool for the first time
  - Updating existing docs to reflect current state
```

with:

```
  Common tasks include:
  - Updating the VitePress docs site (docs/) after infrastructure changes
  - Writing or updating READMEs for services and tools
  - Documenting a service, chart, or tool for the first time
  - Updating existing docs to reflect current state
```

Remove the entire ADR block:

```
  When writing ADRs:
  - Follow the existing ADR format in the repo (check docs/adrs/ or similar)
  - Include Status, Context, Decision, and Consequences sections
  - Reference related ADRs if they exist
```

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/docs.yaml
git commit -m "refactor(agent-platform): scope docs recipe to docs site and READMEs"
```

---

### Task 8: Update `deep-plan.yaml` — add agents and composition patterns

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml`

**Step 1: Add new agents to Available Agents section**

After the existing `- qa-test:` line, add:

```
    - web-research: General-purpose research on any topic. Produces gists with structured findings.
    - critic: Reviews upstream output for gaps, errors, unverified claims. Validation gate.
    - trip-planner: Plans trips with day-by-day itineraries. Produces gists.
    - idea-capture: Captures freeform ideas as structured docs in the repo. Creates PRs.
    - claude-config: Improves Claude Code configuration (CLAUDE.md, settings, skills). Creates PRs.
    - adr-writer: Authors Architecture Decision Records with proper template. Creates PRs.
    - docs: Creates or updates documentation, READMEs, and VitePress docs site. Creates PRs.
    - helm-chart-dev: Creates or updates Helm charts, subcharts, and values files. Creates PRs.
    - dep-upgrade: Upgrades dependencies with breaking change checks. Creates PRs.
    - scaffold: Scaffolds new services with Bazel, Helm chart, and ArgoCD app. Creates PRs.
```

**Step 2: Add Composition Patterns section**

After the `## Available Agents` section, before `## Iteration Context`, add:

```
    ## Composition Patterns
    Common DAG shapes to consider when designing pipelines:
    - research → critic: Validated infrastructure findings
    - web-research → critic: Validated external research
    - web-research → trip-planner: Travel planning with pre-research
    - code-fix → critic → pr-review: Reviewed, validated code fixes
    - feature → qa-test → pr-review: Feature with test coverage and review
    - web-research → adr-writer: Research-backed architecture decisions
    - research → code-fix → critic: Investigate, fix, validate
    - ci-debug → qa-test: Fix CI then verify test coverage
    - dep-upgrade → qa-test → pr-review: Upgrade with tests and review

    Use critic as a validation gate after any agent that produces analysis or
    research. Use pr-review as the final gate for any pipeline that produces code.
    Don't over-split — 2-5 steps is the sweet spot.
```

**Step 3: Commit**

```bash
git add projects/agent_platform/goose_agent/image/recipes/deep-plan.yaml
git commit -m "feat(agent-platform): add composition patterns and new agents to deep-plan"
```

---

### Task 9: Add agent entries to `chart/values.yaml`

**Files:**

- Modify: `projects/agent_platform/chart/values.yaml`

**Step 1: Add 6 new agent entries after the `qa-test` block (line ~597)**

Add entries for each new agent. Follow the exact structure of existing entries.
Key differences:

- `critic` and `adr-writer` get `model: claude-opus-4-6` (like `deep-plan`)
- `trip-planner` and `idea-capture` don't get the context-forge extension
- Each agent's recipe content must match its YAML file exactly

**Step 2: Update docs agent entry**

Find the existing docs agent entry in values.yaml and update its `desc` and `recipe`
content to match the modified `docs.yaml` (no ADR references).

**Step 3: Update deep-plan agent entry**

Find the existing deep-plan agent entry in values.yaml and update its `recipe`
content to match the modified `deep-plan.yaml` (new agents + composition patterns).

**Step 4: Commit**

```bash
git add projects/agent_platform/chart/values.yaml
git commit -m "feat(agent-platform): add 6 new agent entries to orchestrator config"
```

---

### Task 10: Bump chart version

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml`
- Modify: `projects/agent_platform/deploy/application.yaml`

**Step 1: Bump Chart.yaml version**

Read the current version in `Chart.yaml` and bump the minor version (e.g. 0.20.1 → 0.21.0).

**Step 2: Update application.yaml targetRevision**

Update `targetRevision` in `deploy/application.yaml` to match the new Chart.yaml version.

**Step 3: Commit**

```bash
git add projects/agent_platform/chart/Chart.yaml projects/agent_platform/deploy/application.yaml
git commit -m "chore(agent-platform): bump chart version for new agent recipes"
```

---

### Task 11: Run format and validate

**Step 1: Run format**

```bash
cd /tmp/claude-worktrees/new-agent-recipes && format
```

**Step 2: Commit any format changes**

```bash
git add -A && git commit -m "style: format" || true
```

---

### Task 12: Push and create PR

**Step 1: Push branch**

```bash
git push -u origin feat/new-agent-recipes
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(agent-platform): add 6 new agent recipes with DAG composition" --body "$(cat <<'EOF'
## Summary
- Add 6 new goose agent recipes: web-research, critic, trip-planner, idea-capture, claude-config, adr-writer
- Update deep-plan with composition patterns for DAG pipeline planning
- Scope docs recipe to VitePress/READMEs (ADRs handled by adr-writer)
- critic and adr-writer use Opus for critical thinking / judgment calls

## New agents

| Agent | Category | Model | Output |
|-------|----------|-------|--------|
| web-research | analyse | sonnet | gist |
| critic | validate | opus | gist |
| trip-planner | action | sonnet | gist |
| idea-capture | action | sonnet | pr |
| claude-config | action | sonnet | pr |
| adr-writer | action | opus | pr |

## Composition patterns added to deep-plan
- research → critic: Validated infrastructure findings
- web-research → critic: Validated external research
- code-fix → critic → pr-review: Reviewed, validated fixes
- feature → qa-test → pr-review: Feature with test coverage and review

## Test plan
- [ ] CI passes recipe_validate_test.go (schema, goose-result blocks, template vars)
- [ ] New agents appear in orchestrator /agents API
- [ ] Deep-plan references new agents in Available Agents section
- [ ] Pipeline composer can select new agents from dropdown

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
