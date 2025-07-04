# ArgoCD GitOps Migration - Ready for Implementation

This directory contains a complete, production-ready ArgoCD GitOps migration from the current Skaffold + GitHub Actions deployment system.

## 🎯 Current Status: READY FOR DEPLOYMENT

**✅ Completed:**
- Helm-based ArgoCD installation with official charts
- 1Password Connect operator integration
- ApplicationSet for automatic service discovery
- GitHub authentication configuration
- Complete minikube testing environment
- Bootstrap and credential rotation workflows
- Migration documentation and cleanup scripts

**📋 What This Replaces:**
- Scheduled GitHub Actions deployments (every 30 minutes)
- Manual Skaffold runs via self-hosted runner
- External Secrets CRD (replaced with 1Password operator)
- Manual secret management in workflows

## 🚀 Deployment Instructions

### Prerequisites

1. **Set GitHub Secrets** (see [GITHUB_SECRETS.md](GITHUB_SECRETS.md)):
   - `GITHUB_TOKEN` - Personal Access Token with repo scope
   - `ONEPASSWORD_CONNECT_HOST` - 1Password Connect server URL
   - `ONEPASSWORD_CONNECT_TOKEN` - 1Password Connect API token

2. **Enable Workflows:**
   ```bash
   mv .github/workflows/bootstrap-argocd.yaml.disabled .github/workflows/bootstrap-argocd.yaml
   mv .github/workflows/rotate-onepassword-creds.yaml.disabled .github/workflows/rotate-onepassword-creds.yaml
   ```

### Option 1: GitHub Actions Bootstrap (Recommended)

1. Go to Actions → "Bootstrap ArgoCD GitOps"
2. Run workflow with your cluster context
3. Use `dry_run: true` first to validate
4. Run with `dry_run: false` to deploy

### Option 2: Local Helm Bootstrap

```bash
# Set environment variables
export ONEPASSWORD_CONNECT_HOST="your-connect-host"
export ONEPASSWORD_CONNECT_TOKEN="your-connect-token"
export GITHUB_TOKEN="your-github-pat"

# Run bootstrap
./argocd/helm/bootstrap.sh
```

### Option 3: Manual Step-by-Step

```bash
# Add Helm repos
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add 1password https://1password.github.io/connect-helm-charts
helm repo update

# Install ArgoCD
helm install argocd argo/argo-cd \
  --namespace argocd --create-namespace \
  --values argocd/helm/argocd/values.yaml

# Configure GitHub access (replace with your token)
kubectl create secret generic homelab-repo-secret \
  --namespace argocd \
  --from-literal=url=https://github.com/jomcgi/homelab.git \
  --from-literal=username=jomcgi \
  --from-literal=password="your-github-token"
kubectl label secret homelab-repo-secret -n argocd argocd.argoproj.io/secret-type=repository

# Install 1Password (replace with your values)
helm install onepassword-connect 1password/connect \
  --namespace onepassword --create-namespace \
  --set connect.connectHost="your-host" \
  --set connect.connectToken="your-token" \
  --set operator.create=true

# Apply ApplicationSet
kubectl apply -f argocd/apps/homelab-services.yaml
```

## 🧪 Testing

Test the complete setup in minikube:

```bash
cd argocd/test
./helm-test.sh
```

## 📋 Post-Deployment Cleanup

After successful ArgoCD deployment:

1. **Remove old workflows:**
   ```bash
   ./argocd/cleanup-old-workflows.sh
   ```

2. **Verify ArgoCD is managing services:**
   - Check ArgoCD UI for all discovered applications
   - Verify sync status is healthy
   - Test a deployment by updating a service

3. **Monitor first sync cycle:**
   - Watch for any permission or authentication issues
   - Check 1Password operator secret synchronization
   - Verify Kaniko builds work for container services

## 🔄 What Happens After Deployment

**✅ Benefits:**
- **No more scheduled jobs** - ArgoCD pulls changes automatically
- **Self-healing deployments** - ArgoCD auto-corrects drift
- **Container builds** - Kaniko builds happen in-cluster via pre-sync hooks
- **Secure secrets** - 1Password operator manages all secrets
- **GitOps compliance** - All changes tracked in Git
- **Better observability** - ArgoCD UI shows deployment status

**📊 Service Discovery:**
- ApplicationSet automatically discovers all services in `cluster/services/*`
- Each service gets its own ArgoCD Application
- Sync happens when files change in Git
- Container services trigger Kaniko builds before deployment

## 🚨 Rollback Plan

If issues occur, you can quickly rollback:

1. **Re-enable old workflows:**
   ```bash
   git checkout HEAD~1 -- .github/workflows/k8s-deploy-*.yaml
   ```

2. **Uninstall ArgoCD:**
   ```bash
   helm uninstall argocd -n argocd
   helm uninstall onepassword-connect -n onepassword
   kubectl delete namespace argocd onepassword
   ```

3. **Resume old deployment pattern** until issues are resolved

## 🛠️ Architecture

```
GitHub Repository (homelab)
├── cluster/services/*          ← ApplicationSet discovers these
├── argocd/
│   ├── helm/bootstrap.sh       ← Complete setup script
│   ├── apps/homelab-services.yaml ← Service discovery
│   └── GITHUB_SECRETS.md       ← Required secrets
└── .github/workflows/
    ├── bootstrap-argocd.yaml   ← One-time setup
    └── rotate-*-creds.yaml     ← Maintenance
```

**Data Flow:**
1. Developer pushes code → GitHub
2. ArgoCD detects changes → Triggers sync
3. For containers: Kaniko builds → Pushes image
4. ArgoCD applies manifests → Updates cluster
5. 1Password operator → Syncs secrets

## 🔐 Security Notes

- GitHub PAT has minimal required scope (`repo`)
- 1Password tokens scoped to necessary vaults only
- ArgoCD runs with least-privilege RBAC
- All secrets encrypted at rest
- Audit logs available in ArgoCD UI

## 📞 Support

If you encounter issues:
1. Check ArgoCD UI for application sync status
2. Review 1Password operator logs: `kubectl logs -n onepassword deployment/onepassword-operator`
3. Check ApplicationSet controller: `kubectl logs -n argocd deployment/argocd-applicationset-controller`
4. Validate GitHub connectivity in ArgoCD UI under Settings → Repositories

---

**Ready to modernize your homelab GitOps! 🚀**