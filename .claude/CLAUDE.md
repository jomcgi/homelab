# CLAUDE.md - Secure Kubernetes Homelab

## Before Starting Work

| Task | Action |
|------|--------|
| Reading 10+ files | Use `/opencode` (FREE local Qwen) |
| Generating boilerplate | Use `/opencode` |
| Research across codebase | Use `/opencode` |
| Complex reasoning | Use Claude (you) |

See `.claude/skills/opencode/SKILL.md` for full guidance.

## Development Workflow Requirements

**NEVER make changes directly on the main branch.** All modifications MUST:
1. Create a new worktree: `git worktree add /tmp/claude-worktrees/<feature-name> -b <feature-branch>`
2. Make changes in the worktree
3. Create a PR before any commits are pushed
4. Only merge after review/approval

**Why:** Direct main branch changes break GitOps workflows and bypass CI/CD checks.

## Architecture Reference

Import these when relevant:

- [architecture/security.md](../architecture/security.md) - Container security, network security, secrets
- [architecture/observability.md](../architecture/observability.md) - Kyverno auto-injection, OTEL, Linkerd, SigNoz
- [architecture/services.md](../architecture/services.md) - Service overview (cluster-critical, prod, dev)
- [architecture/contributing.md](../architecture/contributing.md) - Adding services, common tasks

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

| Command | Purpose |
|---------|---------|
| `format` | Format code, update lock files (apko, Python) |
| `lstr -L 2 <path>` | Directory tree viewer |

## GitOps Application Structure

Services are organized in `overlays/<env>/<service>/`:
- `application.yaml` - ArgoCD Application pointing to Helm chart
- `kustomization.yaml` - Makes app discoverable by ArgoCD
- `values.yaml` - Environment-specific Helm value overrides

ArgoCD syncs from `clusters/homelab/kustomization.yaml` which references environment overlays.

## Anti-Patterns to Avoid

- **Cargo-culting** Kubernetes best practices without understanding why
- **Over-engineering** simple services
- **Running as root** unnecessarily
- **Direct internet exposure** bypassing Cloudflare
