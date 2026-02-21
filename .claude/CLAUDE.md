# CLAUDE.md - Secure Kubernetes Homelab

## Repository

Hosted at **https://github.com/jomcgi/homelab**. The `gh` CLI is authenticated:

```bash
gh issue list
gh issue view <number>
gh pr create --title "..." --body "..."
gh pr view <number>
```

## Repository Structure

```
homelab/
├── charts/              # Helm charts (27 charts: argocd, signoz, trips, grimoire, ...)
├── overlays/            # Environment-specific overrides
│   ├── cluster-critical/  # Core infra (argocd, cert-manager, linkerd, longhorn, signoz)
│   ├── dev/               # Development services (grimoire, marine, stargazer)
│   └── prod/              # Production services (trips, knowledge-graph, nats, ...)
├── operators/           # Custom Kubernetes operators (Go, controller-runtime)
│   ├── cloudflare/        # Cloudflare DNS/tunnel operator
│   └── oci-model-cache/   # ML model caching operator
├── services/            # Application source code (Go, Python)
├── websites/            # Frontend apps (Vite + React, Astro) — JS, not TypeScript
├── tools/               # Build tooling (Bazel macros, OCI helpers, scripts)
├── architecture/        # Design docs (security, observability, services, contributing)
├── clusters/            # Kustomization entry point for ArgoCD
├── MODULE.bazel         # Bazel dependency management (bzlmod, not WORKSPACE)
└── buildbuddy.yaml      # CI pipeline definition
```

**Languages:** Go, Python, JavaScript, Starlark (BUILD files)

## Essential Commands

```bash
# ALWAYS use bazelisk, not bazel directly (.bazelversion manages version)
bazelisk build //...          # Build everything
bazelisk test //...           # Test everything
format                        # Format code + update all lock files (apko, pip, gazelle)
bazelisk run gazelle          # Regenerate BUILD files after adding Go imports

# Render Helm templates (NEVER helm install — GitOps only)
helm template <release> charts/<chart>/ -f overlays/<env>/<service>/values.yaml

# Push container images
bazelisk run //charts/<service>/image:push
```

**Vendored tools** (available via `direnv allow`): `format`, `argocd`, `helm`, `crane`, `kind`, `go`, `python`, `pnpm`, `node`, `buildifier`, `buildozer`

## Development Workflow

**NEVER commit directly to main.** All changes MUST go through a worktree + PR:

1. `git -C ~/repos/homelab worktree add -b feat/my-feature /tmp/claude-worktrees/my-feature origin/main`
2. Make changes in `/tmp/claude-worktrees/my-feature`
3. Commit, push, create PR
4. Merge after CI passes

## Context Loading Rules

- **Security changes**: Read `architecture/security.md` FIRST
- **New services**: Read `architecture/contributing.md` + `architecture/services.md`
- **Observability work**: Read `architecture/observability.md`
- **Operator changes**: Read `operators/best-practices.md`

## Key Patterns

| Pattern | Implementation |
|---------|---------------|
| **Secrets** | 1Password Operator (`OnePasswordItem` CRD) — never hardcode |
| **Container images** | apko + rules_apko (not Dockerfiles) — always dual-arch (x86_64 + aarch64) |
| **Auto image updates** | ArgoCD Image Updater (`imageupdater.yaml` in overlay) |
| **Package deps (Python)** | `@pip//package` via aspect_rules_py (not `requirement()`) |
| **Package deps (JS)** | pnpm + rules_js |
| **Non-root containers** | uid 65532 convention, `runAsNonRoot: true` |

## Kubernetes Operations (kubectl)

**CRITICAL: This cluster is managed via GitOps. kubectl is READ-ONLY.**

Safe operations: `get`, `describe`, `logs`, `top`, `explain`, `api-resources`

**FORBIDDEN** — modify Git instead: `apply`, `patch`, `edit`, `scale`, `delete`

To make changes: edit `overlays/<env>/<service>/values.yaml` → commit → push → ArgoCD auto-syncs (~5-10s).

## GitOps Application Structure

Services live in `overlays/<env>/<service>/`:

- `application.yaml` — ArgoCD Application pointing to `charts/<chart>` with Helm values
- `kustomization.yaml` — Makes app discoverable (`resources: [application.yaml]`)
- `values.yaml` — Environment-specific Helm value overrides
- `imageupdater.yaml` — (optional) ArgoCD Image Updater config

ArgoCD syncs from `clusters/homelab/kustomization.yaml` → environment overlays.

**Environments:** `cluster-critical` (infra), `dev` (development), `prod` (production)

## Continuous Integration

CI uses **BuildBuddy Workflows** (not GitHub Actions). Defined in `buildbuddy.yaml`.

Runs on every push/PR:
- **Format check** — formatters + gazelle, verifies no uncommitted changes
- **Test and push** — `bazel test //...`, pushes images on main branch

Debug CI failures: use `/buildbuddy` skill or reproduce locally with `bazelisk test //... --config=ci`

Static sites deploy via `.github/workflows/cf-pages-*.yaml` (requires self-hosted runners).

## Anti-Patterns

- **Using `bazel` instead of `bazelisk`** — bazelisk manages versions via .bazelversion
- **Using Dockerfiles** — this repo uses apko exclusively for container images
- **Running as root** — always use non-root (uid 65532)
- **Direct internet exposure** — all traffic goes through Cloudflare
- **Running tests outside Bazel** — no `pytest`, `go test`, `npm test` directly
- **Using `@rules_python` syntax** — this repo uses `@aspect_rules_py`
- **Over-engineering** simple services
