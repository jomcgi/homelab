# RFC: Self-Hosted Autonomous Coding Agents via OpenHands

**Author:** Joe McGinley
**Status:** Draft
**Created:** 2026-02-25

---

## Pitch

Stripe ships 1,000+ AI-authored PRs per week using internal "Minion" agents — isolated sandboxes that take a task description, write code, run CI, and open a PR with zero human interaction in between. Ona (formerly Gitpod) sells the same pattern as a product. Both are closed-source.

OpenHands is an MIT-licensed platform that implements this exact workflow. It has a native Kubernetes runtime that spawns ephemeral sandbox pods per task, a model-agnostic agent engine, and a web UI for submitting and reviewing work. The proprietary layer they sell on top is multi-tenant infrastructure (user RBAC, SSO, PostgreSQL) — none of which matters for a single-user homelab deployment where auth is handled by Cloudflare Zero Trust before traffic ever hits the cluster.

The proposal: deploy OpenHands on the existing 5-node K8s cluster using only MIT-licensed components. Agents get isolated pods, LLM inference routes through an in-cluster LiteLLM proxy backed by a Claude Max subscription (flat-rate, no per-token cost), and the whole thing is managed as an ArgoCD Application.

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
agents.jomcgi.dev (Cloudflare Zero Trust)
         |
         v
+- Namespace: ingress ------------------------------------------+
|  Cloudflare Tunnel ConfigMap                                   |
|  (shared across all services, route added via values overlay)  |
|  - hostname: agents.jomcgi.dev                                 |
|    service: http://openhands.openhands.svc.cluster.local:3000  |
+----------------------------------------------------------------+
         |
         v
+- Namespace: openhands ----------------------------------------+
|                                                                |
|  OnePasswordItem: openhands-secrets                            |
|  +- LITELLM_MASTER_KEY (proxy auth)                            |
|  +- SANDBOX_ENV_GITHUB_TOKEN (forwarded to sandboxes)          |
|  +- SANDBOX_ENV_BUILDBUDDY_API_KEY (forwarded)                 |
|                                                                |
|  OnePasswordItem: claude-sdk-token                             |
|  +- CLAUDE_AUTH_TOKEN (sk-ant-oat01-* from claude setup-token) |
|                                                                |
|  Deployment: litellm-claude-sdk (1 replica)                    |
|  +- ghcr.io/cabinlab/litellm-claude-code                       |
|  +- CLAUDE_AUTH_TOKEN from claude-sdk-token Secret              |
|  +- LITELLM_MASTER_KEY from openhands-secrets Secret            |
|  Service: litellm-claude-sdk (ClusterIP:4000)                  |
|                                                                |
|  Deployment: openhands-app (1 replica)                         |
|  +- OpenHands app image                                        |
|  +- RUNTIME=kubernetes                                         |
|  +- LLM_BASE_URL=http://litellm-claude-sdk:4000/v1             |
|  +- LLM_API_KEY=$LITELLM_MASTER_KEY                            |
|  +- Secret env vars from OnePasswordItem                       |
|  +- ServiceAccount: openhands-agent --------------------------+-- K8s API
|                                                                |   (pod CRUD)
|  Service: openhands (ClusterIP:3000)                           |       |
|  PVC: openhands-data (conversation history)                    |       |
+----------------------------------------------------------------+       |
                                                                         v
+- Namespace: openhands-sandboxes ------------------------------------+
|  Labels: linkerd.io/inject=disabled                                  |
|                                                                      |
|  LimitRange: default per-pod resource bounds                         |
|  ResourceQuota: bound max concurrent sandboxes                       |
|                                                                      |
|  Kyverno injects tools volume into every sandbox pod                 |
|                                                                      |
|  [ephemeral pods created/destroyed per task]                          |
|  +-----------------------------------------------------------------+ |
|  | sandbox-a (runtime)                                              | |
|  | +- OpenHands runtime image (upstream, unmodified)                | |
|  | +- /usr/local/tools (image volume, read-only)                    | |
|  |    +- ghcr.io/jomcgi/homelab/openhands-tools:latest              | |
|  |    +- bb (aliased as bazel/bazelisk), go, pnpm, node             | |
|  | +- Env vars injected at runtime by app:                          | |
|  |    +- GITHUB_TOKEN (from SANDBOX_ENV_GITHUB_TOKEN)               | |
|  |    +- BUILDBUDDY_API_KEY (from SANDBOX_ENV_BUILDBUDDY_...)       | |
|  +-----------------------------------------------------------------+ |
+----------------------------------------------------------------------+
```

### Ingress

The OpenHands web UI is exposed at `agents.jomcgi.dev` via the existing shared Cloudflare Tunnel. No per-service annotations or ingress resources — just a route in the tunnel's ConfigMap, added via the `overlays/prod/cloudflare-tunnel/values.yaml` overlay:

```yaml
- hostname: agents.jomcgi.dev
  service: http://openhands.openhands.svc.cluster.local:3000
```

Cloudflare Zero Trust handles authentication at the edge before traffic reaches the cluster.

### RBAC

The app pod's ServiceAccount needs a Role in the sandboxes namespace. The KubernetesRuntime creates pods, services, PVCs, and ingresses per session — all permissions are required:

- `pods`: create, get, list, watch, delete
- `pods/log`: get
- `pods/exec`: create
- `services`: create, get, delete (runtime + VSCode services per sandbox)
- `persistentvolumeclaims`: create, get, list, delete (workspace PVC per sandbox)
- `ingresses` (networking.k8s.io): create, get, delete (VSCode ingress per sandbox)

This is what the proprietary chart sets up. We replicate it with a Role + RoleBinding (~30 lines of YAML).

### Resource Limits

The `openhands-sandboxes` namespace gets both a `LimitRange` (per-pod defaults) and a `ResourceQuota` (namespace-wide cap) from day one. A runaway `bazel build` inside a sandbox must not starve other homelab workloads on the 5-node cluster.

**LimitRange** (applied to every sandbox pod that doesn't specify its own limits):

| Resource | Request | Limit |
|---|---|---|
| CPU | 1 | 4 |
| Memory | 2Gi | 8Gi |

**ResourceQuota** (namespace-wide aggregate):

| Resource | Max |
|---|---|
| pods | 5 |
| requests.cpu | 8 |
| requests.memory | 16Gi |

These are starting values — generous enough for compilation workloads but bounded enough to protect the cluster. The OpenHands K8s runtime config also has `resource_cpu_request`, `resource_memory_request`, and `resource_memory_limit` which are set on sandbox pods at creation time. These should be configured to match or fall within the LimitRange.

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
| `LITELLM_MASTER_KEY` | Auth key for OpenHands -> LiteLLM proxy requests |
| JWT secret | Web UI session authentication |

**LiteLLM proxy secrets** (separate Deployment, never reach sandboxes):

| Secret | Purpose |
|---|---|
| `CLAUDE_AUTH_TOKEN` | Long-lived Claude Max subscription token (`sk-ant-oat01-*` from `claude setup-token`) |
| `LITELLM_MASTER_KEY` | Validates incoming requests from OpenHands |

**Sandbox-forwarded secrets** via `SANDBOX_ENV_*` prefix — any env var on the app pod prefixed with `SANDBOX_ENV_` is automatically forwarded to every sandbox with the prefix stripped:

| App Pod Env Var | Sandbox Env Var | Purpose |
|---|---|---|
| `SANDBOX_ENV_GITHUB_TOKEN` | `GITHUB_TOKEN` | Git clone, PR creation |
| `SANDBOX_ENV_BUILDBUDDY_API_KEY` | `BUILDBUDDY_API_KEY` | Remote build execution via bb CLI |

All secrets are sourced from 1Password via `OnePasswordItem` CRDs, consistent with every other service in the cluster. The `OnePasswordItem` creates a K8s Secret in the `openhands` namespace, which is mounted as env vars on the app Deployment. No secrets are stored in Git or config files.

### LLM Provider

LLM inference routes through an in-cluster LiteLLM proxy with a Claude Agent SDK custom provider ([`litellm-claude-code`](https://github.com/cabinlab/litellm-claude-code)). This uses the official Claude Agent SDK — the same SDK that powers Claude Code — authenticated against an existing Claude Max subscription via a long-lived token generated by `claude setup-token`. The proxy exposes an OpenAI-compatible `/v1` endpoint as a ClusterIP Service. OpenHands connects to it as a standard LiteLLM provider.

The flow:

```
OpenHands app → LiteLLM proxy (ClusterIP:4000) → Claude Agent SDK provider → Claude API (Max subscription auth)
```

**Why a proxy instead of direct API keys**: A Claude Max subscription provides flat-rate access to Claude models with no per-token cost — critical for autonomous agent loops that can burn through millions of tokens per task. The Claude Agent SDK is the officially supported way to use subscription auth programmatically. Since OpenHands uses LiteLLM internally for provider abstraction, `litellm-claude-code` bridges the gap by making the Claude Agent SDK available through LiteLLM's standard OpenAI-compatible interface.

**Headless authentication**: The `claude setup-token` command performs a one-time browser-based OAuth flow and outputs a long-lived token (`sk-ant-oat01-*`). This token is stored in a `OnePasswordItem` and injected into the LiteLLM proxy pod as `CLAUDE_AUTH_TOKEN`. No ongoing browser sessions or interactive auth required.

**OpenHands LLM config**:

| Setting | Value |
|---|---|
| `LLM_BASE_URL` | `http://litellm-claude-sdk:4000/v1` |
| `LLM_API_KEY` | `$LITELLM_MASTER_KEY` (proxy auth, not a Claude key) |
| `LLM_MODEL` | `claude-opus-4-6` (default) |

**Multi-model support**: The LiteLLM proxy serves all Claude models through the same endpoint — the model is selected per-request, not per-deployment. OpenHands supports configuring multiple models: a primary model for the agent loop and an optional cheaper/faster model for condensation (context compaction). With flat-rate Max subscription pricing, there's no cost penalty for defaulting to the most capable model. The recommended configuration:

| Role | Model | Rationale |
|---|---|---|
| Primary agent | `claude-opus-4-6` | Most capable model — no cost penalty on Max subscription, best reasoning for autonomous coding |
| Fast tasks | `claude-sonnet-4-6` | Available for simpler tasks where speed matters more than depth — selectable per-task in the UI |
| Condensation | `claude-haiku-4-5-20251001` | Fast model for summarizing conversation history when context window fills |

Users can switch between Opus and Sonnet per-task via the OpenHands web UI without any infrastructure changes — the proxy handles all models through the same `LLM_BASE_URL`.

**Fallback**: Direct Anthropic API keys can be configured as an alternative provider if the proxy or subscription auth has issues. OpenHands' LiteLLM integration supports multiple providers natively.

---

## Security Deviations

This deployment intentionally violates several principles from [`architecture/security.md`](../security.md). Each deviation is required by the OpenHands runtime and is scoped to the `openhands` and `openhands-sandboxes` namespaces only.

### Sandbox pods run as root

The KubernetesRuntime hardcodes `override_user_id=0, override_username='root'` when launching sandbox pods. The `runtime_init.py` script uses `useradd`, writes to `/etc/sudoers`, and modifies `/etc/pam.d/su` — all of which require root. This violates:

- `runAsNonRoot: true`
- `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true`
- `capabilities.drop: [ALL]`

**Mitigation**: Sandbox pods are ephemeral (destroyed after each task), run in an isolated namespace with a ResourceQuota, and have no access to cluster secrets or other namespaces. The app pod's ServiceAccount is scoped to `openhands-sandboxes` only.

### Linkerd disabled on sandbox namespace

The existing Kyverno `ClusterPolicy` (`inject-linkerd-namespace-annotation`) auto-annotates new namespaces with `linkerd.io/inject: enabled`. Sandbox pods would receive Linkerd sidecars, which adds latency to pod startup, consumes resources on ephemeral pods, and may interfere with the OpenHands agent-server protocol.

The `openhands-sandboxes` namespace will be created with `linkerd.io/inject: disabled` to opt out. Sandboxes don't communicate with other cluster services — they talk only to the app pod in the `openhands` namespace (which IS meshed). This can be revisited if sandbox-to-service communication is needed in later phases.

### Broader ServiceAccount permissions

The `openhands-agent` ServiceAccount has create/delete on pods, services, PVCs, and ingresses in the sandboxes namespace. This is wider than typical homelab services which only need to serve traffic, not manage K8s resources. The permissions are scoped to a single namespace via a Role (not ClusterRole).

---

## Rollout

### Phase 1 — Working Agent Loop
- Deploy app + KubernetesRuntime with upstream runtime image
- `OnePasswordItem` for `LITELLM_MASTER_KEY` + `SANDBOX_ENV_*` secrets (GitHub PAT, BuildBuddy API key)
- `OnePasswordItem` for `CLAUDE_AUTH_TOKEN` (`sk-ant-oat01-*` from `claude setup-token`)
- Deploy `litellm-claude-code` proxy: Deployment + ClusterIP Service on port 4000
- Configure OpenHands LLM settings: `LLM_BASE_URL=http://litellm-claude-sdk:4000/v1`
- `openhands-sandboxes` namespace with `linkerd.io/inject: disabled`, LimitRange, and ResourceQuota
- Cloudflare Tunnel route: `agents.jomcgi.dev` -> `openhands.openhands.svc.cluster.local:3000`
- **Validate PATH injection**: spin up a sandbox pod, inspect `runtime_init.py` behaviour, confirm tools path survives before building tools image
- Build and push apko-based tools image (`openhands-tools`)
- Kyverno policy to inject tools volume into sandbox pods
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

1. **Claude Max token refresh** — the `sk-ant-oat01-*` token from `claude setup-token` is long-lived but not permanent. Need to verify expiration behaviour and whether the LiteLLM proxy handles token refresh gracefully, or whether periodic re-auth via `claude setup-token` is required. If tokens expire during a task, the proxy should return a clear error rather than silently failing.

2. **KubernetesRuntime config specifics** — the README at `openhands/runtime/impl/kubernetes/README.md` documents requirements. Will need to read this carefully during implementation to get namespace, SA, and image pull config right.

3. **PATH injection via Kyverno** — the Kyverno policy injects `/usr/local/tools/bin` into PATH via a container-level env var. However, OpenHands' `runtime_init.py` rewrites `.bashrc` and `/etc/environment` during sandbox setup, and `add_env_vars()` also appends to `.bashrc`. These are three different mechanisms affecting PATH resolution that don't compose predictably — if `runtime_init.py` overwrites PATH entirely rather than appending, the tools volume disappears from the agent's shell. **This must be tested before building the tools image.** Phase 1 validation step: spin up a sandbox pod manually, inspect what `runtime_init.py` does to PATH in `.bashrc` and `/etc/environment`, and confirm whether the container-level env var survives. If it doesn't, fallback options include patching `/etc/profile.d/` via the Kyverno policy or using `runtime_startup_env_vars` to inject the tools path through OpenHands' own config.

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
| [SDK getting started](https://docs.openhands.dev/sdk/getting-started) | Provider config, agent SDK usage |
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

### LiteLLM Claude Code Proxy

| Resource | What You'll Find |
|---|---|
| [`litellm-claude-code`](https://github.com/cabinlab/litellm-claude-code) | Custom LiteLLM provider bridging Claude Agent SDK to OpenAI-compatible API |
| [`claude setup-token`](https://docs.anthropic.com/en/docs/claude-code/cli-usage) | CLI command to generate long-lived auth tokens for headless use |

### Community Context

| Resource | What You'll Find |
|---|---|
| [Issue #6864](https://github.com/All-Hands-AI/OpenHands/issues/6864) | **Ignore** — pre-dates KubernetesRuntime (Feb 2025). DinD sidecar hacks from before native K8s support existed. |
