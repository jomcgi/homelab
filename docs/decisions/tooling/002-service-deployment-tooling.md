# ADR 002: Service Deployment Tooling

**Author:** Joe McGinley
**Status:** Draft
**Created:** 2026-03-08

---

## Problem

Adding a new service to the homelab today requires hand-crafting ~7 files across 4 directories with no scaffolding, no templates, and no shared conventions outside of implicit "copy the previous service" folklore. The process involves:

1. Writing a Helm chart from scratch (`charts/<service>/Chart.yaml`, `templates/`, `values.yaml`)
2. Creating ArgoCD overlay files in `overlays/<env>/<service>/` (3 files: `application.yaml`, `kustomization.yaml`, `values.yaml`)
3. Writing Bazel BUILD files for the service source and container image
4. Manually registering the service in `overlays/<env>/kustomization.yaml`
5. Optionally adding ArgoCD Image Updater config, SigNoz HTTP alerts, and 1Password secret items

This creates three concrete problems:

**1. High onboarding friction.** A developer adding their first service spends hours studying existing services rather than hours writing application logic. The implicit conventions (uid 65532, distroless base, `@pip//` syntax, Pydantic settings patterns, OTel annotations) are not documented in a single discoverable place.

**2. Inconsistent service quality.** Without templates, each service drifts from the established patterns. Security contexts get forgotten, image update automation gets skipped, and OTel configuration varies arbitrarily. Services diverge structurally even when their underlying requirements are identical.

**3. Slow iteration.** Spinning up a new service for experimentation requires the same boilerplate ceremony as a production service. This discourages experimentation and incremental extension of the homelab.

This ADR documents the current state, identifies the specific gaps, and recommends targeted improvements to make "add a new service" a single command.

---

## Current Deployment Patterns

This section records the as-found state of each service type after thorough investigation of the codebase (March 2026).

### Python Services

**Build pattern** — `aspect_rules_py` (not `@rules_python`). The repo uses `@pip//package_name` dependency syntax.

Standard directory structure:

```
services/<service>/
├── BUILD                     # py3_image() target
├── __init__.py
├── app/
│   ├── BUILD                 # py_venv_binary + py_library targets
│   ├── __init__.py
│   ├── main.py               # Entry point (typically FastAPI/FastMCP)
│   ├── config.py             # Pydantic BaseSettings
│   └── <module>.py
└── tests/
    ├── BUILD                 # py_test targets using tools/pytest/defs.bzl
    ├── __init__.py
    ├── conftest.py
    └── <module>_test.py
```

Top-level BUILD file invokes the `py3_image()` macro from `tools/oci/py3_image.bzl`. The macro handles multi-platform builds (amd64 + arm64), non-root execution (uid 65532), Python path setup, and GHCR push targets with stamped CI tags.

Key patterns from production services (`knowledge_graph`, `stargazer`, `agent_orchestrator_mcp`):

- Configuration via `pydantic_settings.BaseSettings` with `env_prefix` or `env_nested_delimiter`
- Modular `py_library` targets per logical concern (`:config`, `:storage`, `:models`)
- Multiple `py_venv_binary` entry points when a service has multiple processes (scraper, embedder, mcp)
- OpenTelemetry instrumentation via `podAnnotations: instrumentation.opentelemetry.io/inject-python: "python"`
- Custom base images supported (e.g., `@gdal_python_base` for geospatial dependencies)
- Semgrep security scanning integrated at each source level via `semgrep_target_test`

**What's automated:** Multi-platform image build, stamped image tags, GHCR push, CI test execution via BuildBuddy, format checking via ruff.

**What's manual:** Everything else — no scaffolding tool generates the initial directory structure or BUILD files.

---

### Go Services

**Build pattern** — `rules_go` with Gazelle for BUILD file generation. All Go sources live in the shared `go.mod` module (`github.com/jomcgi/homelab`).

Standard directory structure:

```
services/<service>/
├── BUILD                     # go_library + go_binary + go_test + go_image()
├── main.go
└── *.go / *_test.go
```

For complex services with multiple packages:

```
services/<service>/
├── BUILD                     # go_image() pointing to cmd/
├── cmd/
│   └── main.go               # main package (thin wiring layer)
└── internal/
    ├── <module>/
    │   ├── BUILD             # go_library per package
    │   └── *.go
    └── ...
```

The `go_image()` macro from `tools/oci/go_image.bzl` wraps a `go_binary` into a multi-platform OCI image using distroless as the base. The binary lands at `/opt/app` with entrypoint set accordingly.

Go operators (`operators/<name>/`) follow kubebuilder conventions with `api/v1/`, `internal/controller/`, `internal/statemachine/`, and `cmd/` subdirectories. Operators use controller-runtime with finalizers, status conditions, and idempotent reconciliation (documented in `operators/best-practices.md`).

Dependency management: `go.mod` is the source of truth. `bazel run //:gazelle` regenerates BUILD files and `use_repo()` entries in `MODULE.bazel`. Gazelle must run via Bazel (not standalone) to correctly resolve `@com_github_*` labels.

**What's automated:** Gazelle regenerates BUILD files from Go imports, multi-platform image builds, GHCR push, CI test execution, format checking via gofumpt.

**What's manual:** Initial directory structure, initial `go_image()` target in BUILD, overlay/chart creation.

---

### MCP Servers

MCP servers are Python services with one additional deployment concern: they must be registered with the Context Forge gateway to become available as tools.

**Two deployment modes:**

| Mode                  | When to use                             | Mechanism                                              |
| --------------------- | --------------------------------------- | ------------------------------------------------------ |
| **Native HTTP**       | Server uses `FastMCP(transport="http")` | Direct Deployment + Service on port 8080               |
| **Translate sidecar** | Server only supports stdio              | IBM `mcpgateway.translate` sidecar wraps stdio as HTTP |

All MCP servers are co-deployed in a single Helm release via `charts/mcp-servers/` — a meta-chart that loops over a `servers:` array in `values.yaml`. Each entry in the array produces: Deployment, Service, ServiceAccount, OnePasswordItem secret, Context Forge registration Job, SigNoz HTTPCheck alert ConfigMap, and optional RBAC resources.

In-repo MCP servers (`todo_mcp`, `buildbuddy_mcp`, `agent_orchestrator_mcp`) are Python services built with `py3_image()`. Their images are pushed to GHCR and referenced in `overlays/prod/mcp-servers/values.yaml`.

**Context Forge registration** happens automatically via a Helm post-install/upgrade Job: the job waits for the gateway, mints a short-lived JWT, and calls `/gateways` to register the server's ClusterIP endpoint. Developers add a `registration:` block to the server entry in `values.yaml`.

**What's automated:** Gateway registration (post-install hook), HTTP health alerting (SigNoz ConfigMap generated by chart), ArgoCD Image Updater (optional flag per server), RBAC generation.

**What's manual:** Adding a new server entry to `overlays/prod/mcp-servers/values.yaml`, writing the Python service code and BUILD files (same as any Python service), adding the image to `overlays/prod/mcp-servers/values.yaml`.

---

### Helm Charts and ArgoCD Deployment

Every service has a dedicated Helm chart in `charts/<service>/`. There is no shared generic chart (except `mcp-servers` which serves as a meta-chart for its server group).

Standard chart structure:

```
charts/<service>/
├── Chart.yaml                # apiVersion: v2, name, version, appVersion
├── values.yaml               # Chart-level defaults
├── README.md
└── templates/
    ├── _helpers.tpl           # {{- define "service.labels" }} etc.
    ├── deployment.yaml
    ├── service.yaml
    ├── serviceaccount.yaml
    ├── onepassworditem.yaml   # 1Password Operator CRD for secrets
    └── ...
```

**ArgoCD overlay structure** (three files per environment per service):

```
overlays/<env>/<service>/
├── application.yaml          # ArgoCD Application pointing to charts/<service>
├── kustomization.yaml        # Single entry: resources: [application.yaml]
└── values.yaml               # Environment-specific Helm value overrides
```

**Service discovery chain:** `clusters/homelab/kustomization.yaml` → `overlays/<env>/kustomization.yaml` → `overlays/<env>/<service>/kustomization.yaml` → `application.yaml`. Every level is explicit — services must be manually added to `overlays/<env>/kustomization.yaml`.

Secrets are managed exclusively via the 1Password Operator (`OnePasswordItem` CRD). The item path convention is `vaults/k8s-homelab/items/<service>`. The operator creates a Kubernetes Secret of the same name, which is mounted via `envFrom.secretRef` in the Deployment.

ArgoCD Image Updater is configured via annotations on the Application resource or a separate `imageupdater.yaml`. When enabled, it monitors GHCR for new image digests, commits the updated digest back to `overlays/<env>/<service>/values.yaml` on `main`, and triggers an ArgoCD sync. This closes the loop from CI image push → live deployment without human intervention.

**Security defaults** (consistent across all charts):

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

**What's automated:** ArgoCD syncs within 5–10s of a git push, image digest updates via Image Updater, namespace creation (`CreateNamespace=true`), self-healing.

**What's manual:** Creating the chart, creating overlay files, adding the service to `overlays/<env>/kustomization.yaml`.

---

### Scaffolding and Templating: Current State

Three tools exist in the `bazel_env` (available via `tools/BUILD`) but are **not actively used for service scaffolding**:

| Tool       | Source                                    | Status                           |
| ---------- | ----------------------------------------- | -------------------------------- |
| `copier`   | `@pip//copier`                            | Available, no templates defined  |
| `scaffold` | `@com_github_hay_kot_scaffold//:scaffold` | Available, no templates defined  |
| `yo`       | `@npm//tools:yo`                          | Available, no generators defined |

No `scripts/` directory, no `Makefile` new-service target, no cookiecutter templates, no documented step-by-step "how to add a service" guide beyond `docs/contributing.md` (which covers contribution workflow, not service creation specifics).

The Bazel macros in `tools/oci/` (`go_image`, `py3_image`, `apko_image`) abstract the image build step well but do not help with the directory layout, chart boilerplate, or overlay registration — the highest-friction parts of service creation.

---

## Decision

Address the tooling gap in two phases, prioritizing the highest-friction steps first.

### Phase 1: Copier Template for New Services

Create a `templates/new-service/` directory with a [Copier](https://copier.readthedocs.io/) template that generates a complete service skeleton from a short questionnaire. Copier is already available in the `bazel_env` and is the most capable of the three available templating tools (supports Jinja2, conditional files, post-generation tasks).

**Template questionnaire:**

```yaml
# templates/new-service/copier.yaml
service_name:
  type: str
  help: "Service name (kebab-case, e.g. my-service)"

service_type:
  type: str
  choices: [go, python, mcp]
  help: "Service language/type"

environment:
  type: str
  choices: [dev, prod, both]
  help: "Target deployment environment"

has_secrets:
  type: bool
  default: true
  help: "Does this service need a 1Password secret item?"

enable_image_updater:
  type: bool
  default: true
  help: "Enable ArgoCD Image Updater for automatic digest updates?"

enable_otel:
  type: bool
  default: true
  help: "Enable OpenTelemetry instrumentation?"
```

**Generated output:**

```
charts/<service_name>/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── service.yaml
    ├── serviceaccount.yaml
    └── onepassworditem.yaml          # if has_secrets=true

overlays/<env>/<service_name>/
├── application.yaml
├── kustomization.yaml
├── values.yaml
└── imageupdater.yaml                 # if enable_image_updater=true

services/<service_name>/              # if type=python or mcp
├── BUILD
├── __init__.py
└── app/
    ├── BUILD
    ├── __init__.py
    ├── main.py
    └── config.py

services/<service_name>/              # if type=go
├── BUILD
└── main.go
```

**Post-generation task** (Copier's `_tasks` hook): append the service to `overlays/<env>/kustomization.yaml` — the most error-prone manual step.

**Usage:**

```bash
copier copy templates/new-service/ .
```

Copier is idempotent on re-run: it only updates files that have drifted from the template, making it useful for applying convention updates across existing services.

### Phase 2: Document and Enforce Conventions

Conventions discovered during this investigation are currently implicit. Make them explicit and enforceable:

**2a. Service creation guide** — Add `docs/services.md` section "Adding a New Service" with:

- When to use `go_image` vs `py3_image` vs `apko_image`
- The 7 files every service needs and what goes in each
- How to name 1Password vault items
- How to configure OTel annotations
- How to run `bazel run //:gazelle` after adding Go deps

**2b. Template tests** — Add `bazel run //templates/new-service:validate` that:

- Runs `copier copy` with each combination of options into a temp dir
- Runs `helm lint` on the generated chart
- Checks that `kustomize build clusters/homelab` still resolves (catches broken kustomization registration)

**2c. Helm chart linting in CI** — Add `helm lint charts/...` to `buildbuddy.yaml`. Currently, chart rendering errors are only caught when ArgoCD tries to sync. Fail fast in CI instead.

### Out of Scope

- **A generic "one chart to rule them all"** — The per-service chart pattern provides better isolation and clearer ownership. The `mcp-servers` meta-chart is appropriate for a cohesive server group that shares deployment infrastructure. Do not generalize further.
- **Auto-discovery of services** — Explicit registration in `kustomization.yaml` is intentional. It prevents accidental deployment of services and makes the list of deployed services auditable.
- **Replacing the macro layer** — `go_image`, `py3_image`, and `apko_image` are well-designed and provide the right abstraction. The gap is above them (chart + overlay creation), not below.

---

## Consequences

### If implemented

**Positive:**

- "Add a new service" becomes a 2-minute task for experienced developers and a 15-minute task for new contributors (down from 1–3 hours)
- New services automatically comply with security defaults (non-root, RO filesystem, capability drops), OTel configuration, and image update automation — because the template encodes these patterns
- Convention drift is caught earlier: the validate target in CI fails if a generated service diverges from the template, and re-running `copier copy` on existing services surfaces drift
- Encourages experimentation: low ceremony means developers spin up throwaway services to test ideas rather than hacking into existing ones

**Negative/risks:**

- Templates require maintenance — when conventions change (e.g., a new OTel annotation format), the template must be updated and `copier copy` re-run on existing services. This is manual work, not automatic.
- The Copier template is a second source of truth alongside real services. If a real service diverges from the template for a legitimate reason, Copier will report false-positive drift on re-runs. Template answers must be checkpointed in `.copier-answers.yml` per service.
- Phase 2 (Helm linting in CI) may surface existing chart issues that block PRs. Accept this cost — it's better to find issues in CI than in production.

### If not implemented

The status quo continues: each service added by hand, conventions erode over time, new contributors struggle, and experimentation is discouraged by ceremony. The existing tools (`copier`, `scaffold`) remain available but unused — a wasted investment in tool distribution.

---

## References

| Resource                                                              | Relevance                                                               |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [Copier documentation](https://copier.readthedocs.io/)                | Template engine used in this proposal                                   |
| [`tools/oci/py3_image.bzl`](../../../tools/oci/py3_image.bzl)         | Python image macro — template generates invocations of this             |
| [`tools/oci/go_image.bzl`](../../../tools/oci/go_image.bzl)           | Go image macro — template generates invocations of this                 |
| [`docs/contributing.md`](../../contributing.md)                       | Existing contribution guide (Phase 2 extends this)                      |
| [`docs/services.md`](../../services.md)                               | Existing service architecture doc (Phase 2 adds "Adding a New Service") |
| [`operators/best-practices.md`](../../../operators/best-practices.md) | Operator-specific patterns (inform Go operator variant of template)     |
| [`charts/mcp-servers/`](../../../charts/mcp-servers/)                 | MCP meta-chart — reference for MCP server onboarding path               |
| [ADR 001: OCI Tool Distribution](./001-oci-tool-distribution.md)      | Establishes `copier` as an available tool in the developer environment  |
