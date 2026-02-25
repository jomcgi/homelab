# RFC: Self-Hosted Autonomous Coding Agents via OpenHands

**Author:** Joe McGinley
**Status:** Draft
**Created:** 2026-02-25

---

## Pitch

Stripe ships 1,000+ AI-authored PRs per week using internal "Minion" agents — isolated sandboxes that take a task description, write code, run CI, and open a PR with zero human interaction in between. Ona (formerly Gitpod) sells the same pattern as a product. Both are closed-source.

OpenHands is an MIT-licensed platform that implements this exact workflow. It has a native Kubernetes runtime that spawns ephemeral sandbox pods per task, a model-agnostic agent engine, and a web UI for submitting and reviewing work. The proprietary layer they sell on top is multi-tenant infrastructure (user RBAC, SSO, PostgreSQL) — none of which matters for a single-user homelab deployment where auth is handled by Cloudflare Zero Trust before traffic ever hits the cluster.

The proposal: deploy OpenHands on the existing 5-node K8s cluster using only MIT-licensed components. Agents get isolated pods, LLM inference runs through a Codex subscription (flat-rate, no per-token cost), and the whole thing is managed as an ArgoCD Application.

---

## How Stripe's Minions Actually Work

Understanding the architecture we're replicating:

1. **Trigger**: Engineer tags a bot in Slack with a task description
2. **Context prefetch**: A deterministic orchestrator scans the thread for links, pulls Jira tickets, searches code via Sourcegraph/MCP. Curates ~15 relevant tools from 400+ available (giving the LLM all 400 causes token paralysis)
3. **Sandbox**: Each agent gets its own isolated VM — the same devboxes human engineers use. Easy to spin up, disposable, no access to production data
4. **Agent loop**: An LLM (reportedly a fork of an open-source agent) writes code, runs linters (<5s feedback), then selective CI (not all 3M tests — only relevant ones)
5. **Pragmatic cap**: If tests fail, error goes back to the agent. Capped at 2 retry attempts — if it can't fix it in 2 tries, a third won't help. Flags a human instead of burning compute
6. **Output**: Clean PR following Stripe's templates, green CI, ready for human review

The key insight: the agent itself is nearly a commodity. The value is in the **infrastructure** — sandboxing, context curation, CI feedback loops, and guardrails.

---

## Why OpenHands

OpenHands maps directly onto the Stripe pattern:

| Stripe Layer | OpenHands Equivalent |
|---|---|
| Isolated devbox per agent | KubernetesRuntime — ephemeral pod per task |
| Agent loop with tool use | Software Agent SDK — agent loop, compaction, tool orchestration |
| Slack trigger -> PR output | Web UI / REST API -> GitHub integration |
| CI feedback to agent | Sandbox has terminal access, agent runs tests and reads output |
| Context from internal tools | MCP server support, microagent system |
| Human review gate | Agent opens PR, human reviews as normal |

### What's MIT-Licensed (everything we need)

- **Software Agent SDK** (`openhands-sdk`) — the agent engine: loop, tools, context management, compaction across context windows
- **Agent Server** (`openhands-agent-server`) — REST/WebSocket API, session lifecycle
- **KubernetesRuntime** (`openhands/runtime/impl/kubernetes/`) — creates sandbox pods via K8s API, communicates over agent-server protocol, cleans up on completion. Shipped in v0.45.0 (June 2025, PR #8814). This is the same runtime their production SaaS uses.
- **Web GUI** — React SPA with editor, terminal, file browser
- **CLI** — terminal-based agent interaction
- **Docker images** — `openhands` (app) and `agent-server` (runtime)

### What's Proprietary (and why we skip it)

The [OpenHands Cloud Helm chart](https://github.com/All-Hands-AI/OpenHands-Cloud) (Polyform Free Trial, 30 days/year) adds:

- Multi-user auth / SSO / SAML -> **Cloudflare Zero Trust handles this**
- User-to-user RBAC / isolation -> **single user, N/A**
- PostgreSQL for multi-user sessions -> **file-based persistence is fine**
- Centralized billing / usage tracking -> **N/A**
- NetworkPolicy between user sandboxes -> **no multi-tenant concern**

---

## Architecture

```
Cloudflare Zero Trust (auth at edge)
         |
         v
+- Namespace: openhands --------------------------------+
|                                                        |
|  OnePasswordItem: openhands-secrets                    |
|  +- LLM_API_KEY (Codex sub / Anthropic key)            |
|  +- SANDBOX_ENV_GITHUB_TOKEN (forwarded to sandboxes)  |
|  +- SANDBOX_ENV_BUILDBUDDY_API_KEY (forwarded)         |
|                                                        |
|  Deployment: openhands-app (1 replica)                 |
|  +- OpenHands app image                                |
|  +- RUNTIME=kubernetes                                 |
|  +- Secret env vars from OnePasswordItem               |
|  +- ServiceAccount: openhands-agent -------------------+-- K8s API
|                                                        |   (pod CRUD)
|  Service: openhands (ClusterIP:3000)                   |       |
|  PVC: openhands-data (conversation history)            |       |
+--------------------------------------------------------+       |
                                                                 v
+- Namespace: openhands-sandboxes --------------------------------+
|                                                                  |
|  Kyverno injects tools volume into every sandbox pod             |
|                                                                  |
|  [ephemeral pods created/destroyed per task]                      |
|  +-------------------------------------------------------------+ |
|  | sandbox-a (runtime)                                          | |
|  | +- OpenHands runtime image (upstream, unmodified)            | |
|  | +- /usr/local/tools (image volume, read-only)                | |
|  |    +- ghcr.io/jomcgi/homelab/openhands-tools:latest          | |
|  |    +- bb (aliased as bazel/bazelisk), go, pnpm, node         | |
|  | +- Env vars injected at runtime by app:                      | |
|  |    +- GITHUB_TOKEN (from SANDBOX_ENV_GITHUB_TOKEN)           | |
|  |    +- BUILDBUDDY_API_KEY (from SANDBOX_ENV_BUILDBUDDY_...)   | |
|  +-------------------------------------------------------------+ |
|                                                                  |
|  ResourceQuota: bound max concurrent sandboxes                   |
+------------------------------------------------------------------+
```

### RBAC (the only non-trivial K8s config)

The app pod's ServiceAccount needs a Role in the sandboxes namespace:

- `pods`: create, get, list, watch, delete
- `pods/log`: get
- `pods/exec`: create

This is what the proprietary chart sets up. It's ~20 lines of YAML.

### Sandbox Tooling Strategy

OpenHands sandbox pods use a pre-built runtime image (`runtime_container_image`) that includes the agent engine, Python, micromamba, and VSCode Server. We use this image unmodified — no custom builds on top of their base.

Project-specific tooling (Go, BuildBuddy CLI, pnpm, etc.) is delivered via a **separate OCI image mounted as a Kubernetes image volume**. K8s 1.31+ supports mounting OCI images directly as read-only volumes — no initContainers or copy steps required. The tooling image is built with apko (Wolfi packages + static binaries) and managed as a standard Bazel target.

A Kyverno `ClusterPolicy` injects the tools volume into every sandbox pod:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: inject-openhands-tools
spec:
  rules:
    - name: inject-tools-volume
      match:
        resources:
          kinds: [Pod]
          selector:
            matchLabels:
              app: openhands-runtime
      mutate:
        patchStrategicMerge:
          spec:
            containers:
              - name: runtime
                volumeMounts:
                  - name: tools
                    mountPath: /usr/local/tools
                    readOnly: true
                env:
                  - name: PATH
                    value: "/usr/local/tools/bin:$(PATH)"
            volumes:
              - name: tools
                image:
                  reference: ghcr.io/jomcgi/homelab/openhands-tools:latest
                  pullPolicy: IfNotPresent
```

This separation means:

- **Runtime image stays upstream** — easier upgrades, no rebuild on OpenHands releases
- **Tools image is apko-built** — consistent with the rest of the repo, dual-arch, non-root, reproducible
- **Tools update independently** — push a new tools image without touching OpenHands config
- **Image volumes are cached per node** — pulled once, mounted read-only into every sandbox pod

The tools image includes:

| Tool | Purpose | Alias |
|---|---|---|
| BuildBuddy CLI (`bb`) | Build + test via remote execution | `bazel`, `bazelisk` |
| Go | Build/test Go services and operators | — |
| pnpm + Node.js | Build websites/ frontend apps | — |
| git | Already in runtime, but pinned version in tools | — |

### Secret Management

OpenHands does not use Kubernetes Secrets on sandbox pods. The app pod is the trust boundary — it holds all secrets and injects them into sandboxes at runtime via shell commands (`export` + `.bashrc` append). This means secrets flow through two paths:

**App-only secrets** (never reach sandboxes):

| Secret | Purpose |
|---|---|
| LLM API key | Model inference (Codex subscription or Anthropic API) |
| JWT secret | Web UI session authentication |

**Sandbox-forwarded secrets** via `SANDBOX_ENV_*` prefix — any env var on the app pod prefixed with `SANDBOX_ENV_` is automatically forwarded to every sandbox with the prefix stripped:

| App Pod Env Var | Sandbox Env Var | Purpose |
|---|---|---|
| `SANDBOX_ENV_GITHUB_TOKEN` | `GITHUB_TOKEN` | Git clone, PR creation |
| `SANDBOX_ENV_BUILDBUDDY_API_KEY` | `BUILDBUDDY_API_KEY` | Remote build execution via bb CLI |

All secrets are sourced from 1Password via `OnePasswordItem` CRDs, consistent with every other service in the cluster. The `OnePasswordItem` creates a K8s Secret in the `openhands` namespace, which is mounted as env vars on the app Deployment. No secrets are stored in Git or config files.

### LLM Provider

OpenHands supports a `subscription_login()` flow that authenticates against an existing ChatGPT Plus/Pro subscription to use Codex models without API credits:

```python
from openhands.sdk import LLM
llm = LLM.subscription_login(vendor="openai", model="gpt-5.2-codex")
```

This makes autonomous agent loops effectively **zero marginal cost** at the LLM layer. Can also bring Anthropic API keys or point at local Ollama for flexibility.

---

## Rollout

### Phase 1 — Working Agent Loop
- Deploy app + KubernetesRuntime with upstream runtime image
- `OnePasswordItem` for LLM key + `SANDBOX_ENV_*` secrets (GitHub PAT, BuildBuddy API key)
- Build and push apko-based tools image (`openhands-tools`)
- Kyverno policy to inject tools volume into sandbox pods
- Cloudflare Tunnel for access
- Codex subscription as provider
- Submit tasks via web GUI, verify sandbox pods spin up and produce PRs
- **Success criteria**: end-to-end flow from task -> sandbox pod -> committed code, with `bazel test` working inside the sandbox

### Phase 2 — Integration
- GitHub App for PR workflows
- OTel traces to SigNoz
- Persistent conversation history via PVC

### Phase 3 — Automation
- Slack webhook for fire-and-forget submission
- GitHub webhook to auto-assign agents to labelled issues
- ResourceQuota tuning based on observed sandbox resource usage

---

## Open Questions for Implementation

1. **Sandbox resource limits** — what CPU/memory per pod? Code compilation vs simple edits have very different profiles. Start permissive, observe, tighten.

2. **Codex subscription_login() durability** — relatively new feature. Need to verify token refresh and rate limit behaviour during long-running autonomous tasks.

3. **KubernetesRuntime config specifics** — the README at `openhands/runtime/impl/kubernetes/README.md` documents requirements. Will need to read this carefully during implementation to get namespace, SA, and image pull config right.

4. **PATH injection via Kyverno** — the `env` patch in the Kyverno policy adds `/usr/local/tools/bin` to PATH. Need to verify this works with OpenHands' runtime_init.py user setup, which rewrites `.bashrc` and `/etc/environment`. May need the tools path in both places.

---

## References

### The Pattern We're Replicating

| Resource | Why It Matters |
|---|---|
| [Stripe Minions Part 1](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | High-level one-shot agent architecture |
| [Stripe Minions Part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) | Implementation: blueprints, CI feedback, tool curation |
| [Medium: Stripe's 6-layer architecture](https://medium.com/@janithprabhash/beyond-copilot-how-stripes-autonomous-ai-minions-merge-1-000-prs-a-week-9eb7838c562d) | Context prefetching, MCP integration, tiered CI, retry caps |
| [The Register: Gitpod -> Ona](https://www.theregister.com/2025/09/03/gitpod_rebrands_as_ona/) | Ona's pivot, VPC deployment, agent modes |

### OpenHands — Start Here During Implementation

| Resource | What You'll Find |
|---|---|
| [OpenHands GitHub repo](https://github.com/All-Hands-AI/OpenHands) | Source. KubernetesRuntime lives at `openhands/runtime/impl/kubernetes/` |
| [`runtime/impl/kubernetes/README.md`](https://github.com/All-Hands-AI/OpenHands/blob/main/openhands/runtime/impl/kubernetes/README.md) | **Read this first** — config requirements for the K8s runtime |
| [`runtime/base.py`](https://github.com/All-Hands-AI/OpenHands/blob/main/openhands/runtime/base.py) | Runtime base class, shows all 4 built-in implementations |
| [Release 0.45.0 changelog](https://github.com/All-Hands-AI/OpenHands/releases/tag/0.45.0) | When KubernetesRuntime shipped (PR #8814) |
| [SDK getting started](https://docs.openhands.dev/sdk/getting-started) | Includes `subscription_login()` for Codex, provider config |
| [Sandbox overview (V1)](https://docs.openhands.dev/openhands/usage/sandboxes/overview) | Sandbox providers, `RUNTIME` env var |
| [Configuration options (V1)](https://docs.openhands.dev/openhands/usage/advanced/configuration-options) | Env vars: `RUNTIME`, `OH_PERSISTENCE_DIR`, `SANDBOX_VOLUMES` |
| [Runtime architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime) | Client-server model, image building, action execution |
| [Custom sandbox guide](https://docs.openhands.dev/openhands/usage/advanced/custom-sandbox-guide) | Custom base images for project-specific tooling |

### OpenHands — Proprietary Chart (Reference Only)

| Resource | What You'll Find |
|---|---|
| [OpenHands-Cloud Helm chart](https://github.com/All-Hands-AI/OpenHands-Cloud) | What the paid chart does — useful to understand the full resource set |
| [Self-hosted blog post](https://openhands.dev/blog/openhands-cloud-self-hosted-secure-convenient-deployment-of-ai-software-development-agents) | Licensing rationale, Polyform Free Trial terms |
| [DeepWiki: Product Variants](https://deepwiki.com/OpenHands/OpenHands/1.3-product-variants) | Enterprise K8s architecture, required resources table |

### Community Context

| Resource | What You'll Find |
|---|---|
| [Issue #6864](https://github.com/All-Hands-AI/OpenHands/issues/6864) | **Ignore** — pre-dates KubernetesRuntime (Feb 2025). DinD sidecar hacks from before native K8s support existed. |
