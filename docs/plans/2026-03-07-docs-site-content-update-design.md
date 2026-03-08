# Design: docs.jomcgi.dev Content Update

## Problem

The docs site launched with content gaps: 8 deployed services are undocumented, several pages have stale wording, the observability page omits the OTel Operator, and ADR navigation is broken.

## Approach

Hybrid: add missing services to existing tiers in `services.md`, fix wording across pages, and create a new `architecture/agents.md` for the agent platform story. Create an ADR index page for navigation.

## Changes

### 1. services.md — Add Missing Services

**Core Infrastructure (cluster-critical):**

| Service                | Purpose                                               |
| ---------------------- | ----------------------------------------------------- |
| Agent Sandbox          | Controller for isolated agent execution pods          |
| OpenTelemetry Operator | Auto-instrumentation for Go, Python, Node.js services |

**Production Services (prod):**

| Service         | Purpose                                                  |
| --------------- | -------------------------------------------------------- |
| Context Forge   | IBM MCP gateway for aggregating tool servers             |
| Goose Sandboxes | Goose agent sandbox deployments                          |
| LiteLLM         | LLM API proxy for agents (routes to llama-cpp, external) |
| MCP OAuth Proxy | OAuth 2.1 auth layer for remote MCP access               |
| MCP Servers     | Consolidated ArgoCD, K8s, BuildBuddy, SigNoz MCP servers |

**Development Services (dev):**

| Service  | Purpose                             |
| -------- | ----------------------------------- |
| Grimoire | D&D knowledge management with Redis |

**Static Websites:**

| Site            | Description                                              |
| --------------- | -------------------------------------------------------- |
| docs.jomcgi.dev | Architecture docs and ADRs (VitePress, Cloudflare Pages) |

### 2. services.md — Wording Fixes

- cert-manager: change to "X.509 certificate management; required by Linkerd for mTLS"
- 1Password Operator: add "(installed via Helm, outside ArgoCD)"

### 3. observability.md — Add OTel Operator

Update pod creation flow diagram to show three layers:

1. **Kyverno Policies** — OTEL env vars + Linkerd namespace annotation (unchanged)
2. **OpenTelemetry Operator** (new) — language-specific auto-instrumentation sidecars via `Instrumentation` CRDs (Go eBPF, Python auto-instrument, Node.js require hook)
3. **Linkerd Proxy Injection** (renumbered) — mTLS + distributed tracing

Add new subsection "3. OTel Operator Auto-Instrumentation (Language-Level)" explaining how the Operator injects init containers and how it complements Kyverno env vars.

### 4. security.md — 1Password Note

Add to Layer 5: "Installed via Helm outside ArgoCD — the only cluster component not managed by GitOps."

### 5. contributing.md — Root App-of-Apps

Add sentence to ArgoCD Discovery Flow: "The `canada` Application is the root app-of-apps that bootstraps all three environments."

### 6. New File: architecture/agents.md

Agent platform overview covering:

- Component map: agent-sandbox → goose-sandboxes → litellm → context-forge + mcp-servers → mcp-oauth-proxy
- Data flow diagram showing agent request traversal
- How the pieces compose (controller, runtime, LLM, tools, auth)

### 7. New File: architecture/decisions/index.md

ADR index page listing all categories and linking to individual ADRs.

### 8. VitePress Config + Homepage

- Re-add "ADRs" to top nav linking to `/architecture/decisions/`
- Re-add "ADRs" hero action on homepage
- Add "Agent Platform" to sidebar under Architecture
- Ensure `decisions/index.md` is captured by the architecture BUILD glob

## Files Modified

- `architecture/services.md`
- `architecture/observability.md`
- `architecture/security.md`
- `architecture/contributing.md`
- `architecture/agents.md` (new)
- `architecture/decisions/index.md` (new)
- `websites/docs.jomcgi.dev/.vitepress/config.js`
- `websites/docs.jomcgi.dev/index.md`
