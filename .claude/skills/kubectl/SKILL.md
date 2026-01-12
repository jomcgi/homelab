---
name: kubectl
description: Use when inspecting Kubernetes cluster state, viewing pod logs, debugging deployments, or checking resource status. Provides READ-ONLY access to the GitOps-managed homelab cluster.
---

# Kubernetes Cluster Access (kubectl)

## CRITICAL: Read-Only Access

This cluster is managed via **GitOps with ArgoCD**. All resource modifications MUST go through Git.

kubectl is available for **inspection and debugging only**.

## Allowed Operations

### Viewing Resources

```bash
kubectl get pods -n <namespace>
kubectl get deployments -n <namespace>
kubectl get services -n <namespace>
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
kubectl get all -n <namespace>
```

### Inspecting Details

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl describe deployment <name> -n <namespace>
kubectl describe service <name> -n <namespace>
```

### Viewing Logs

```bash
kubectl logs <pod-name> -n <namespace>
kubectl logs -f <pod-name> -n <namespace>              # follow
kubectl logs <pod-name> -n <namespace> --previous      # crashed container
kubectl logs -l app=<label> -n <namespace>             # by label
```

### Resource Usage

```bash
kubectl top pods -n <namespace>
kubectl top nodes
```

### Debugging

```bash
kubectl port-forward svc/<service> 8080:80 -n <namespace>
kubectl exec -it <pod-name> -n <namespace> -- /bin/sh
kubectl run debug --image=busybox --rm -it -- sh
```

### Triggering Existing Jobs

```bash
kubectl create job --from=cronjob/<name> <job-name> -n <namespace>
```

## Forbidden Operations

**NEVER modify resources directly:**

```bash
kubectl apply ...      # NO - commit to Git instead
kubectl patch ...      # NO - commit to Git instead
kubectl edit ...       # NO - commit to Git instead
kubectl delete ...     # NO - remove from Git instead
kubectl scale ...      # NO - modify values.yaml instead
kubectl set image ...  # NO - modify values.yaml instead
```

## Why Read-Only?

Direct modifications create **configuration drift** between Git (source of truth) and the cluster. ArgoCD will either:
- Revert your changes automatically (auto-sync enabled)
- Show the application as "OutOfSync" indefinitely

## Making Changes

To modify cluster resources:
1. Edit the appropriate files in Git (charts/, overlays/)
2. Use the `worktree` skill for worktree workflow
3. Commit and push, then create PR with `gh-pr` skill
4. ArgoCD auto-syncs within seconds
5. Verify with read-only kubectl commands

## Common Namespaces

| Namespace | Purpose |
|-----------|---------|
| `argocd` | GitOps controller |
| `claude` | Claude Code deployment |
| `signoz` | Observability stack |
| `linkerd` | Service mesh |
| `longhorn-system` | Distributed storage |
| `cert-manager` | Certificate management |
| `kyverno` | Policy engine |
