# CLAUDE.md - Secure Kubernetes Homelab

## Repository

Hosted at **https://github.com/jomcgi/homelab**. The `gh` CLI is authenticated.

## Repository Structure

```
homelab/
├── projects/            # All services, operators, websites — colocated with deploy configs
│   ├── {service}/         # Each service has chart/, deploy/, src/ as needed
│   │   ├── chart/         # Helm chart (if custom)
│   │   └── deploy/        # ArgoCD Application, values, kustomization
│   └── home-cluster/      # Auto-generated ArgoCD root kustomization
├── charts/              # Shared/upstream Helm charts — ls to discover available charts
├── bazel/               # All Bazel build infrastructure (rules, tools, images, semgrep)
├── docs/               # Design docs, ADRs, and plans — ls to discover available docs
│   └── decisions/       # Architecture Decision Records — ls decisions/<category>/
├── MODULE.bazel         # Bazel dependency management (bzlmod, not WORKSPACE)
└── buildbuddy.yaml      # CI pipeline definition
```

**Languages:** Go, Python, JavaScript, Starlark (BUILD files)

## Essential Commands

```bash
# Local development (no Bazel needed)
format                        # Format code + update BUILD files (standalone)
helm template <release> charts/<chart>/ -f projects/<service>/deploy/values.yaml  # Render Helm templates (NEVER helm install)

# CI-only (runs remotely via BuildBuddy)
bazel test //...              # Test everything
bazel run //charts/<service>/image:push  # Push container images
```

Bazel runs **remotely via BuildBuddy CI** — not locally. Shell aliases route `bazel`/`bazelisk` to the BuildBuddy CLI (`bb`). Locally, use `format` for formatting + BUILD file generation, and push to let CI handle builds/tests.

**Vendored tools** (available via `./bootstrap.sh` + `direnv allow`): `format`, `helm`, `crane`, `kind`, `go`, `python`, `pnpm`, `node`, `buildifier`, `buildozer`, `ruff`, `gofumpt`, `shfmt`, `prettier`, `gazelle`

## Development Workflow

**NEVER commit directly to main.** All changes MUST go through a worktree + PR.

The main repo at `~/repos/homelab` auto-fetches every 60s — always use worktrees for active development.

1. `git -C ~/repos/homelab worktree add -b feat/my-feature /tmp/claude-worktrees/my-feature origin/main`
2. Make changes in `/tmp/claude-worktrees/my-feature`
3. Commit, push, create PR
4. Merge after CI passes

**PR merge method:** This repo only allows **rebase merging** — use `gh pr merge --rebase` (or `--auto --rebase`). Squash and merge commits are disabled.

**Auto-merge for small bug fixes:** For small, focused fixes (e.g. one-line config changes, typo fixes), enable auto-merge with `gh pr merge --auto --rebase`. After enabling, follow through:

1. Poll `gh pr view <number> --json state,mergeStateStatus` until CI passes and the PR merges
2. Poll the rollout (via MCP tools) to verify the fix is live and working

**PR safety:** Always verify PR state (`gh pr view --json state`) before pushing additional commits. Never push to a merged branch — create a new worktree instead.

**Commit messages MUST use [Conventional Commits](https://www.conventionalcommits.org/) format.** A `commit-msg` hook enforces this.

Format: `<type>(<optional scope>): <description>`

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

Examples:

- `feat: add health check endpoint for auth service`
- `fix(signoz): correct trace sampling configuration`
- `ci: add conventional commit pre-commit hook`
- `docs: update observability runbook`

Breaking changes: add `!` after type/scope — `feat!: redesign auth token format`

**Plan & design files:** The brainstorming and writing-plans skills save to `docs/plans/`. Create a worktree **before** saving any plan or design documents — they must land on the feature branch, not main. A PreToolUse hook enforces this.

## Context Loading Rules

- **Security changes**: Read `docs/security.md` FIRST
- **New services**: Read `docs/contributing.md` + `docs/services.md`
- **Observability work**: Read `docs/observability.md`
- **Alerting work**: Read `docs/observability-alerting.md`
- **Operator changes**: Read `projects/operators/best-practices.md`
- **Design proposals**: Check `docs/decisions/` for ADRs (numbered per category)

## Key Patterns

| Pattern                   | Implementation                                                             |
| ------------------------- | -------------------------------------------------------------------------- |
| **Secrets**               | 1Password Operator (`OnePasswordItem` CRD) — never hardcode                |
| **Container images**      | apko + rules_apko (not Dockerfiles) — always dual-arch (x86_64 + aarch64)  |
| **Auto image updates**    | ArgoCD Image Updater (`imageupdater.yaml` in `projects/{service}/deploy/`) |
| **Package deps (Python)** | `@pip//package` via aspect_rules_py (not `requirement()`)                  |
| **Package deps (JS)**     | pnpm + rules_js                                                            |
| **Non-root containers**   | uid 65532 convention, `runAsNonRoot: true`                                 |

## Cluster Investigation

**MCP-first.** PreToolUse hooks enforce using MCP tools (via Context Forge) instead of CLI commands. Use `ToolSearch` with `+kubernetes`, `+argocd`, `+buildbuddy`, or `+signoz` to load tools. Tool names below are shortened — actual IDs have the `mcp__context-forge__` prefix (e.g., `mcp__context-forge__kubernetes-mcp-resources-list`).

| Need                 | Tool                                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| **K8s resources**    | `kubernetes-mcp-resources-list`, `kubernetes-mcp-resources-get`, `kubernetes-mcp-pods-list`               |
| **K8s logs**         | `kubernetes-mcp-pods-log` (recent), SigNoz tools (historical)                                             |
| **K8s metrics**      | `kubernetes-mcp-pods-top`, `kubernetes-mcp-nodes-top`                                                     |
| **ArgoCD apps**      | `argocd-mcp-list-applications`, `argocd-mcp-get-application`, `argocd-mcp-sync-application`               |
| **ArgoCD resources** | `argocd-mcp-get-application-resource-tree`, `argocd-mcp-get-application-managed-resources`                |
| **BuildBuddy CI**    | `buildbuddy-mcp-get-invocation`, `buildbuddy-mcp-get-log`, `buildbuddy-mcp-get-target`                    |
| **Logs**             | `signoz-search-logs`, `signoz-search-logs-by-service`, `signoz-get-error-logs`                            |
| **Traces**           | `signoz-search-traces-by-service`, `signoz-aggregate-traces`, `signoz-get-trace-details`                  |
| **Metrics**          | `signoz-search-metric-by-text`, `signoz-list-metric-keys`                                                 |
| **Services**         | `signoz-list-services`, `signoz-get-service-top-operations`                                               |
| **Dashboards**       | `signoz-list-dashboards`, `signoz-get-dashboard`                                                          |
| **Alerts**           | `signoz-list-alerts`, `signoz-get-alert`, `signoz-get-alert-history`                                      |
| **Agent jobs**       | `agent-orchestrator-mcp-submit-job`, `agent-orchestrator-mcp-list-jobs`, `agent-orchestrator-mcp-get-job` |

## Kubernetes Operations (kubectl)

**CRITICAL: This cluster is managed via GitOps. MCP tools are primary for reads — hooks enforce this.**

Allowed kubectl commands (not covered by MCP): `explain`, `api-resources`, `port-forward`, `exec`, `cp`, `run`, `label`, `annotate`, `auth`, `config`, `version`, `wait`

**FORBIDDEN** — modify Git instead: `apply`, `patch`, `edit`, `scale`, `delete`

**Redirected to MCP** — hooks block these: `get`, `describe`, `logs`, `top`

To make changes: edit `projects/<service>/deploy/values.yaml` → commit → push → ArgoCD auto-syncs (~5-10s).

## GitOps Application Structure

Services are colocated in `projects/{service}/deploy/`:

- `application.yaml` — ArgoCD Application pointing to the service's chart with Helm values
- `kustomization.yaml` — Makes app discoverable (`resources: [application.yaml]`)
- `values.yaml` — Cluster-specific Helm value overrides
- `imageupdater.yaml` — (optional) ArgoCD Image Updater config

ArgoCD root is `projects/home-cluster/kustomization.yaml` (auto-generated by `bazel/images/generate-home-cluster.sh`).

**Adding a new service:** create `projects/{service}/deploy/application.yaml` + `kustomization.yaml`, run `format`, commit.

## Continuous Integration

CI uses **BuildBuddy Workflows** (not GitHub Actions). Defined in `buildbuddy.yaml`.

All builds run **remotely** via BuildBuddy RBE — `bazel`/`bazelisk` is aliased to the BuildBuddy CLI (`bb`).

Runs on every push/PR:

- **Format check** — standalone formatters + gazelle, auto-commits fixes on PR branches (as `ci-format-bot`)
- **Test and push** — `bazel test //...`, pushes images on main branch

Debug CI failures: use `/buildbuddy` skill or reproduce locally with `bazel test //... --config=ci`

Static sites deploy via `bazel run //projects/websites:push_all_pages` on main branch (BuildBuddy CI).

## Anti-Patterns

- **Using Dockerfiles** — this repo uses apko exclusively for container images
- **Running as root** — always use non-root (uid 65532)
- **Direct internet exposure** — all traffic goes through Cloudflare
- **Running tests locally** — tests run in CI via Bazel; no `pytest`, `go test`, `npm test` directly
- **Using `@rules_python` syntax** — this repo uses `@aspect_rules_py`
- **Building a custom Helm chart when upstream provides one** — always check the upstream project repo for an existing chart before creating `charts/<service>/`
- **Using kubectl/argocd CLI for cluster reads** — use MCP tools via Context Forge; PreToolUse hooks enforce this
- **Over-engineering** simple services
