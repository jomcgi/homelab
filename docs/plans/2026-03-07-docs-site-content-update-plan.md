# Docs Site Content Update — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update docs.jomcgi.dev content to reflect the current cluster state — add 8 missing services, fix wording, add OTel Operator to observability docs, create agent platform architecture doc, and fix ADR navigation.

**Architecture:** Edit 4 existing markdown files in `architecture/`, create 2 new ones (`agents.md`, `decisions/index.md`), and update 2 VitePress files for navigation. All content is assembled by the `vitepress_site` Bazel macro from `architecture/` into the docs site.

**Tech Stack:** Markdown, VitePress config (JS), Bazel (`vitepress_filegroup`)

**Worktree:** `/tmp/claude-worktrees/fix-adrs-link` (branch `fix/remove-dead-adrs-link`)

---

### Task 1: Update services.md — Add Missing Services and Fix Wording

**Files:**
- Modify: `architecture/services.md`

**Step 1: Edit the Core Infrastructure table**

Add two rows after the Kyverno row (line 14), maintaining alphabetical order within the table:

```markdown
| **Agent Sandbox**          | Controller for isolated agent execution pods    | [charts/agent-sandbox](../charts/agent-sandbox/)                       |
```

Add after the NVIDIA GPU Operator row (line 16):

```markdown
| **OpenTelemetry Operator** | Auto-instrumentation for Go, Python, Node.js    | [charts/opentelemetry-operator](../charts/opentelemetry-operator/)     |
```

**Step 2: Fix cert-manager and 1Password wording**

Change cert-manager row:
- From: `X.509 certificate management (required by Linkerd)`
- To: `X.509 certificate management; required by Linkerd for mTLS`

Change 1Password Operator row:
- From: `Secret management via OnePasswordItem CRDs              | External chart`
- To: `Secret management via OnePasswordItem CRDs              | External chart (Helm install, outside ArgoCD)`

**Step 3: Add missing Production Services**

Add these rows to the Production Services table, maintaining alphabetical order:

```markdown
| **Context Forge**   | MCP gateway for aggregating tool servers     | [charts/context-forge](../charts/context-forge/)                 |
| **Goose Sandboxes** | Goose agent sandbox deployments              | [charts/goose-sandboxes](../charts/goose-sandboxes/)             |
| **LiteLLM**         | LLM API proxy for agents                     | [charts/litellm](../charts/litellm/)                             |
| **MCP OAuth Proxy** | OAuth 2.1 auth layer for remote MCP access   | [charts/mcp-oauth-proxy](../charts/mcp-oauth-proxy/)             |
| **MCP Servers**     | Consolidated ArgoCD, K8s, BB, SigNoz MCP     | [charts/mcp-servers](../charts/mcp-servers/)                     |
```

**Step 4: Add missing Development Service**

Add to the Development Services table:

```markdown
| **Grimoire**        | D&D knowledge management with Redis              | [charts/grimoire](../charts/grimoire/)                             |
```

**Step 5: Add docs.jomcgi.dev to Static Websites**

Add to the Static Websites table:

```markdown
| **docs.jomcgi.dev** | Architecture docs and ADRs (VitePress, Cloudflare Pages) |
```

**Step 6: Verify build**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed"`
Expected: `Build completed successfully`

**Step 7: Commit**

```bash
git add architecture/services.md
git commit -m "docs(services): add 8 missing services and fix wording"
```

---

### Task 2: Update observability.md — Add OTel Operator Layer

**Files:**
- Modify: `architecture/observability.md`

**Step 1: Update the overview section (lines 7-10)**

Replace:
```markdown
Every service gets automatic observability through two layers:

1. **OTEL Environment Variables** - Application-level instrumentation
2. **Linkerd Service Mesh** - Infrastructure-level tracing
```

With:
```markdown
Every service gets automatic observability through three layers:

1. **OTEL Environment Variables** (Kyverno) - Endpoint configuration for all workloads
2. **OpenTelemetry Operator** - Language-specific auto-instrumentation (Go, Python, Node.js)
3. **Linkerd Service Mesh** - Infrastructure-level distributed tracing and mTLS
```

**Step 2: Update the pod creation flow diagram (lines 16-67)**

Replace the entire diagram with:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Pod Creation Request                         │
│                     (kubectl apply / ArgoCD sync)                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Layer 1: Kyverno Policies                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────┐  ┌───────────────────────────────┐   │
│  │  OTEL Injection Policy   │  │  Linkerd Injection Policy     │   │
│  ├──────────────────────────┤  ├───────────────────────────────┤   │
│  │ Adds env vars:           │  │ Adds namespace annotation:    │   │
│  │ - OTEL_EXPORTER_         │  │   linkerd.io/inject=enabled   │   │
│  │   OTLP_ENDPOINT          │  │                               │   │
│  │ - OTEL_EXPORTER_         │  │ (applies to namespace,        │   │
│  │   OTLP_PROTOCOL=grpc     │  │  affects all pods in it)      │   │
│  └──────────────────────────┘  └───────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Layer 2: OpenTelemetry Operator (opt-in)                │
├─────────────────────────────────────────────────────────────────────┤
│  Instrumentation CRDs deployed per-namespace inject:                │
│  - Go: eBPF auto-instrumentation (autoinstrumentation-go)           │
│  - Python: auto-instrument init container                           │
│  - Node.js: require-hook init container                             │
│                                                                      │
│  Currently enabled for: trips, knowledge-graph, api-gateway,        │
│  mcp-servers, todo, grimoire                                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Layer 3: Linkerd Proxy Injection                   │
├─────────────────────────────────────────────────────────────────────┤
│  Linkerd webhook sees namespace annotation and injects:             │
│  - linkerd-proxy sidecar container                                  │
│  - init container for iptables rules                                │
│  - Additional annotations and labels                                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Running Pod                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────┐          ┌──────────────────────────────┐  │
│  │  Application        │          │  linkerd-proxy sidecar       │  │
│  │  Container          │◄────────►│  (intercepts all traffic)    │  │
│  ├────────────────────┤          ├──────────────────────────────┤  │
│  │ OTEL env vars set   │          │ Sends traces to SigNoz       │  │
│  │ OTel SDK injected   │          │ via control plane            │  │
│  │ (if namespace opted │          │                              │  │
│  │  into Operator)     │          │                              │  │
│  └────────────────────┘          └──────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │  SigNoz Platform │
                       ├──────────────────┤
                       │ - Traces         │
                       │ - Metrics        │
                       │ - Logs           │
                       └──────────────────┘
```

**Step 3: Add new subsection after section 2 (after line 87)**

Insert before the "Observable by Default Philosophy" section:

```markdown
### 3. OTel Operator Auto-Instrumentation (Language-Level)

- **Opt-in per namespace** via `Instrumentation` CRDs
- The OpenTelemetry Operator watches for these CRDs and injects language-specific init containers
- **Go:** eBPF-based — no code changes needed, instruments at the kernel level
- **Python:** Injects `autoinstrumentation-python` init container that patches the runtime
- **Node.js:** Injects `autoinstrumentation-nodejs` init container with require hooks
- Kyverno sets the OTEL endpoint; the Operator provides the SDK — they complement each other
- **Configuration:** `charts/opentelemetry-operator/` with namespace list in overlay values
```

**Step 4: Update the Excluded Namespaces section**

Add `opentelemetry-operator` to the Infrastructure exclusion list.

**Step 5: Verify build**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed"`
Expected: `Build completed successfully`

**Step 6: Commit**

```bash
git add architecture/observability.md
git commit -m "docs(observability): add OTel Operator auto-instrumentation layer"
```

---

### Task 3: Update security.md and contributing.md

**Files:**
- Modify: `architecture/security.md`
- Modify: `architecture/contributing.md`

**Step 1: Add 1Password note in security.md**

In the Layer 5 box (around line 56), after `- Automatic secret rotation support`, add:

```markdown
│  - Installed via Helm outside ArgoCD (only non-GitOps component)    │
```

**Step 2: Add root app-of-apps in contributing.md**

In the ArgoCD Discovery Flow diagram, add to Step 4 (around line 51), before `│  ArgoCD runs "kustomize build"`:

```markdown
│  The "canada" Application is the root app-of-apps.                 │
│  It references all three environment overlays:                      │
```

**Step 3: Verify build**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed"`
Expected: `Build completed successfully`

**Step 4: Commit**

```bash
git add architecture/security.md architecture/contributing.md
git commit -m "docs: add 1Password deployment note and root app-of-apps reference"
```

---

### Task 4: Create architecture/agents.md

**Files:**
- Create: `architecture/agents.md`

**Step 1: Write the agent platform architecture doc**

Create `architecture/agents.md` with:

```markdown
# Agent Platform

This document describes the agent infrastructure running in the cluster.

## Overview

The agent platform enables autonomous AI agents to execute tasks with access to cluster tooling. It spans three environments: a cluster-critical controller, production agent runtimes and tool servers, and development sandboxes.

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Agent Sandbox Controller                         │
│                     (cluster-critical)                               │
├─────────────────────────────────────────────────────────────────────┤
│  Manages lifecycle of isolated agent pods across namespaces         │
│  Charts: charts/agent-sandbox                                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ creates pods
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Runtimes                                │
├──────────────────────────────┬──────────────────────────────────────┤
│  Goose Sandboxes (prod)      │  Grimoire (dev)                      │
│  Autonomous coding agents    │  D&D knowledge management            │
│  charts/goose-sandboxes      │  charts/grimoire                     │
└──────────────────────────────┴──────────────────────────────────────┘
                                 │
                                 │ LLM requests
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           LiteLLM                                    │
│                           (prod)                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Unified LLM API proxy — routes requests to:                        │
│  - llama-cpp (local GPU inference)                                  │
│  - External providers (Anthropic, OpenAI)                           │
│  Charts: charts/litellm                                             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ tool calls
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MCP Tool Infrastructure                           │
│                    (prod, mcp-gateway namespace)                     │
├──────────────────────────────┬──────────────────────────────────────┤
│  Context Forge               │  MCP Servers                         │
│  IBM MCP gateway that        │  Individual tool servers:            │
│  aggregates and routes       │  - ArgoCD MCP                       │
│  tool calls to backends      │  - Kubernetes MCP                   │
│                              │  - BuildBuddy MCP                   │
│  charts/context-forge        │  - SigNoz MCP                       │
│                              │  charts/mcp-servers                  │
├──────────────────────────────┴──────────────────────────────────────┤
│  MCP OAuth Proxy                                                    │
│  OAuth 2.1 auth layer for remote MCP access (e.g., Claude Desktop) │
│  charts/mcp-oauth-proxy                                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow

1. An agent (Goose, Claude Code) needs to perform a cluster operation
2. The agent calls a tool via MCP protocol
3. **Context Forge** receives the call and routes it to the appropriate MCP server
4. The **MCP server** (e.g., Kubernetes MCP) executes the operation against the cluster API
5. Results flow back through Context Forge to the agent

For remote access (e.g., Claude Desktop connecting from outside the cluster):
- Requests first pass through **MCP OAuth Proxy** for authentication
- The proxy validates the OAuth 2.1 token and forwards to Context Forge

## Related ADRs

- [001 - Background Agents](decisions/agents/001-background-agents.md)
- [002 - OpenHands Agent Sandbox](decisions/agents/002-openhands-agent-sandbox.md)
- [003 - Context Forge](decisions/agents/003-context-forge.md)
- [004 - Autonomous Agents](decisions/agents/004-autonomous-agents.md)
- [005 - Role-Based MCP Access](decisions/agents/005-role-based-mcp-access.md)
- [006 - OIDC Auth MCP Gateway](decisions/agents/006-oidc-auth-mcp-gateway.md)
```

**Step 2: Verify build**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed"`
Expected: `Build completed successfully`

**Step 3: Commit**

```bash
git add architecture/agents.md
git commit -m "docs: add agent platform architecture overview"
```

---

### Task 5: Create architecture/decisions/index.md

**Files:**
- Create: `architecture/decisions/index.md`

**Step 1: Write the ADR index page**

Create `architecture/decisions/index.md`:

```markdown
# Architecture Decision Records

ADRs document significant architectural decisions and their context.

## Agents

| ADR | Decision |
|-----|----------|
| [001 - Background Agents](agents/001-background-agents.md) | Kubernetes-native agent execution with sandbox isolation |
| [002 - OpenHands Agent Sandbox](agents/002-openhands-agent-sandbox.md) | OpenHands as the agent runtime framework |
| [003 - Context Forge](agents/003-context-forge.md) | IBM Context Forge as the MCP gateway |
| [004 - Autonomous Agents](agents/004-autonomous-agents.md) | Design for fully autonomous agent workflows |
| [005 - Role-Based MCP Access](agents/005-role-based-mcp-access.md) | Role-based access control for MCP tool servers |
| [006 - OIDC Auth MCP Gateway](agents/006-oidc-auth-mcp-gateway.md) | OAuth 2.1 / OIDC authentication for remote MCP access |

## Docs

| ADR | Decision |
|-----|----------|
| [001 - Static Docs Site](docs/001-static-docs-site.md) | VitePress for architecture documentation |

## Networking

| ADR | Decision |
|-----|----------|
| [001 - Cloudflare Envoy Gateway](networking/001-cloudflare-envoy-gateway.md) | Cloudflare Tunnel + Envoy Gateway for ingress |

## Security

| ADR | Decision |
|-----|----------|
| [001 - Bazel Semgrep](security/001-bazel-semgrep.md) | Semgrep SAST integrated via Bazel rules |
```

Note: The `decisions/index.md` file is already captured by the `glob(["decisions/**/*.md"])` in `architecture/BUILD`, so no BUILD file changes needed.

**Step 2: Verify build**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed|dead link"`
Expected: `Build completed successfully`

**Step 3: Commit**

```bash
git add architecture/decisions/index.md
git commit -m "docs: add ADR index page"
```

---

### Task 6: Update VitePress Config and Homepage

**Files:**
- Modify: `websites/docs.jomcgi.dev/.vitepress/config.js`
- Modify: `websites/docs.jomcgi.dev/index.md`

**Step 1: Re-add ADRs to top nav in config.js**

In the `nav` array, add back the ADRs link (after Architecture, before GitHub):

```javascript
{ text: 'ADRs', link: '/architecture/decisions/' },
```

**Step 2: Add Agent Platform to sidebar in config.js**

In the sidebar Architecture items array, add after Contributing:

```javascript
{ text: 'Agent Platform', link: '/architecture/agents' },
```

**Step 3: Re-add ADRs hero action in index.md**

In the hero actions array, add back between Architecture and GitHub:

```yaml
    - theme: alt
      text: ADRs
      link: /architecture/decisions/
```

**Step 4: Verify build (critical — checks for dead links)**

Run: `bazel build //websites/docs.jomcgi.dev:build 2>&1 | grep -E "ERROR|completed|dead link"`
Expected: `Build completed successfully` with no dead link errors

**Step 5: Run format**

Run: `format`
Expected: No formatting changes (JS/MD should already be clean)

**Step 6: Commit**

```bash
git add websites/docs.jomcgi.dev/.vitepress/config.js websites/docs.jomcgi.dev/index.md
git commit -m "docs: add Agent Platform to sidebar and restore ADR navigation"
```

---

### Task 7: Final Verification and Push

**Step 1: Full build**

Run: `bazel build //websites/docs.jomcgi.dev:build`
Expected: `Build completed successfully`

**Step 2: Run format to check idempotency**

Run: `format && git diff --stat`
Expected: No changes

**Step 3: Push and create PR**

```bash
git push origin fix/remove-dead-adrs-link
```

Then update the existing PR #791 description to cover all changes, or create a new PR if preferred.
