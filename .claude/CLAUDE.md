# CLAUDE.md - Secure Kubernetes Homelab

## Repository

This repo is hosted at **https://github.com/jomcgi/homelab**. The `gh` CLI is authenticated and available — use it for issues, PRs, and code review:

```bash
gh issue list
gh issue view <number>
gh pr create --title "..." --body "..."
gh pr view <number>
```

## Development Workflow Requirements

**NEVER make changes directly on the main branch.** All modifications MUST:

1. Create a new worktree: `git worktree add /tmp/claude-worktrees/<feature-name> -b <feature-branch>`
2. Make changes in the worktree
3. Create a PR before any commits are pushed
4. Only merge after review/approval

**Why:** Direct main branch changes break GitOps workflows and bypass CI/CD checks.

## Parallel Development

Running 3-5 git worktrees with separate Claude sessions is the biggest productivity unlock. Each worktree operates independently, allowing you to work on multiple features simultaneously.

**Setup shell aliases for quick navigation:**

```bash
# Add to ~/.zshrc or ~/.bashrc
alias za='cd /tmp/claude-worktrees/feature-a'
alias zb='cd /tmp/claude-worktrees/feature-b'
alias zc='cd /tmp/claude-worktrees/feature-c'
```

This allows instant switching between worktrees with `za`, `zb`, `zc` commands.

## Learning the Codebase

Run `/config` and enable "Explanatory" output style for Claude to explain its reasoning during changes. This is useful for:

- Onboarding new contributors to the codebase
- Understanding complex architectural decisions
- Learning Kubernetes/GitOps patterns

You can also ask Claude to generate ASCII diagrams or visual explanations of system architecture.

## Context Loading Rules

- **Security changes**: Read architecture/security.md FIRST
- **New services**: Read architecture/contributing.md + architecture/services.md
- **Observability work**: Read architecture/observability.md

## Kubernetes Operations (kubectl)

**CRITICAL: This cluster is managed via GitOps. kubectl is READ-ONLY.**

**Read-only operations** (always safe):

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
kubectl top pods -n <namespace>
```

**FORBIDDEN operations** - modify Git instead:

```bash
kubectl patch deployment ...    # NO
kubectl edit configmap ...       # NO
kubectl scale deployment ...     # NO
kubectl delete deployment ...    # NO
```

**How to make changes:**

1. Modify files in Git (`overlays/<env>/<service>/values.yaml`)
2. Commit and push
3. ArgoCD auto-syncs (5-10 seconds)

## Quick Reference

| Command            | Purpose                                       |
| ------------------ | --------------------------------------------- |
| `format`           | Format code, update lock files (apko, Python) |
| `lstr -L 2 <path>` | Directory tree viewer                         |

## GitOps Application Structure

Services are organized in `overlays/<env>/<service>/`:

- `application.yaml` - ArgoCD Application pointing to Helm chart
- `kustomization.yaml` - Makes app discoverable by ArgoCD
- `values.yaml` - Environment-specific Helm value overrides

ArgoCD syncs from `clusters/homelab/kustomization.yaml` which references environment overlays.

## Continuous Integration

CI is handled by **BuildBuddy** (not GitHub Actions). See `buildbuddy.yaml` in the repo root.

BuildBuddy runs on every push/PR:

- **Format check** - Runs formatters and gazelle, verifies no changes needed
- **Test and push** - Runs `bazel test //...`, pushes images on main branch

To debug failed CI, use the `/buildbuddy` skill to fetch logs via the BuildBuddy API.

### GitHub Actions Workflows

The `.github/workflows/cf-pages-*.yaml` workflows deploy static sites to Cloudflare Pages.
These require **self-hosted runners** (`homelab-runners`) and won't work for external contributors.

## Anti-Patterns to Avoid

- **Cargo-culting** Kubernetes best practices without understanding why
- **Over-engineering** simple services
- **Running as root** unnecessarily
- **Direct internet exposure** bypassing Cloudflare
