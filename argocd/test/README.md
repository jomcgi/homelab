# ArgoCD Testing with Minikube

This directory contains scripts to test the ArgoCD GitOps migration in a local minikube environment.

## Prerequisites

- Docker
- minikube
- kubectl
- Git

## Testing Steps

1. **Setup minikube environment:**
   ```bash
   chmod +x *.sh
   ./setup-minikube.sh
   ```

2. **Deploy ArgoCD:**
   ```bash
   ./deploy-argocd.sh
   ```

3. **Test the deployment:**
   ```bash
   ./test-deployment.sh
   ```

## What Gets Tested

- ArgoCD operator installation
- ArgoCD instance creation
- ApplicationSet service discovery
- Application sync status
- 1Password operator CRDs (operator itself requires real credentials)

## Expected Behavior

- ArgoCD UI should be accessible at `http://localhost:8080`
- ApplicationSet should discover services in `cluster/services/*`
- Applications should attempt to sync (some may fail due to missing secrets/dependencies)
- No critical ArgoCD components should be failing

## Notes

- The 1Password operator will be installed but not functional without real credentials
- Some services may fail to deploy due to missing secrets or external dependencies
- This is expected for testing - we're validating the GitOps structure, not the actual services

## Cleanup

```bash
minikube delete
```