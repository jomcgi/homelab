---
name: dev-deploy
description: Build, push, and deploy a service to an ephemeral test namespace for rapid iteration. Bypasses GitOps intentionally — only deploys to test-* namespaces.
---

# Dev Deploy — Fast Feedback Loop

Build container images, push to GHCR, and helm-install into an ephemeral `test-*` namespace. Completes in under a minute vs 5-10+ minutes through the full GitOps pipeline.

**Safety:** Only deploys to `test-*` namespaces. Never touches dev/prod/cluster-critical namespaces.

## Commands

```
/dev-deploy <service> [--only image1,image2] [--upgrade]
/dev-deploy cleanup <namespace|--all>
/dev-deploy list
```

## Service Registry

Read the service config from `tools/dev-deploy/services.yaml`. This maps each service to its Bazel push targets, Helm chart path, and value override keys.

Available services: `grimoire`, `marine`, `stargazer`, `knowledge-graph`, `todo`

## Deploy Flow

### 1. Load service config

```bash
# Read the service registry (use the Read tool, not cat)
```

Parse the YAML entry for the requested `<service>`. If `--only` is specified, filter the `images[]` list to only matching names.

### 2. Get the dev image tag

```bash
tools/workspace_status.sh | grep STABLE_IMAGE_TAG | awk '{print $2}'
```

This returns a tag like `dev-2026.02.21.14.30.00-a1b2c3d` (dev-prefixed on non-main branches).

Also grab the short SHA for namespace naming:

```bash
git rev-parse --short HEAD
```

### 3. Build and push images

For each image in the service config (or filtered by `--only`):

```bash
bazel run <push_target> --stamp
```

This builds the container image and pushes it to GHCR in one step. The `--stamp` flag applies the `STABLE_IMAGE_TAG` from step 2.

Run each push target sequentially — Bazel handles internal parallelism.

### 4. Create the test namespace

```bash
kubectl create namespace test-<service>-<short-sha>
kubectl label namespace test-<service>-<short-sha> dev-deploy=true
```

Namespace format: `test-<service>-<short-sha>` (e.g., `test-grimoire-a1b2c3d`)

If the namespace already exists and `--upgrade` was specified, skip creation and proceed to helm upgrade in step 6.

### 5. Copy the pull secret

Copy the GHCR pull secret from the `dev` namespace (avoids 1Password operator dependency):

```bash
kubectl get secret ghcr-imagepull-secret -n dev -o json \
  | jq 'del(.metadata.namespace, .metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.managedFields, .metadata.annotations)' \
  | kubectl apply -n test-<service>-<short-sha> -f -
```

### 6. Helm install

Build the helm command from the service config:

```bash
helm install <service> <chart-path> \
  -n test-<service>-<short-sha> \
  -f <base_values>               `# if base_values exists in config` \
  --set imagePullSecrets[0].name=ghcr-imagepull-secret \
  --set <helm_tag_key>=<image-tag> \
  --set <helm_pull_policy_key>=Always \
  `# ... repeat --set for each image` \
  `# ... add each value_override as --set` \
  --wait --timeout 120s
```

If `--upgrade` was specified:

```bash
helm upgrade <service> <chart-path> \
  -n test-<service>-<short-sha> \
  `# ... same flags as install`
```

**Important --set construction:**
- For each image: `--set <helm_tag_key>=<tag> --set <helm_pull_policy_key>=Always`
- For each value_override: `--set <override>`
- Always add: `--set imagePullSecrets[0].name=ghcr-imagepull-secret`

### 7. Verify deployment

```bash
kubectl get pods -n test-<service>-<short-sha>
```

If any pods are not Running/Completed after the `--wait` timeout:

```bash
kubectl describe pod <pod-name> -n test-<service>-<short-sha>
kubectl logs <pod-name> -n test-<service>-<short-sha>
```

### 8. Show access instructions

Suggest port-forward commands based on the services in the chart. For example:

```bash
# Grimoire frontend
kubectl port-forward -n test-grimoire-a1b2c3d svc/grimoire-frontend 8080:8080

# Marine ships-frontend
kubectl port-forward -n test-marine-a1b2c3d svc/marine-frontend 3000:80
```

## Cleanup Flow

### Single namespace

```bash
helm uninstall <service> -n <namespace>
kubectl delete namespace <namespace>
```

### All dev-deploy namespaces

```bash
# List first for confirmation
kubectl get namespaces -l dev-deploy=true

# After user confirms:
kubectl get namespaces -l dev-deploy=true -o name | xargs kubectl delete
```

## List Flow

Show all active dev-deploy namespaces and their helm releases:

```bash
kubectl get namespaces -l dev-deploy=true
```

For each namespace found:

```bash
helm list -n <namespace>
kubectl get pods -n <namespace>
```

## Service-Specific Notes

### grimoire
- Redis deploys alongside (embedded in chart) — no external dependency
- Frontend Nginx proxies `/ws` to the ws-gateway service
- Gemini secret is disabled via value_overrides — AI features won't work but UI loads

### marine
- Requires NATS at `nats://nats.nats.svc.cluster.local:4222` (cross-namespace, must exist)
- AISStream secret disabled — ingest won't connect but API/frontend work
- API needs persistence for SQLite — disabled in test by default, add `--set api.persistence.enabled=true` if needed
- Digest fields must be cleared (done in value_overrides) to avoid tag+digest conflict

### stargazer
- CronJob-based — won't run automatically in test unless you trigger it manually
- To trigger: `kubectl create job --from=cronjob/stargazer test-run -n <namespace>`
- API server disabled by default; use base_values from dev overlay to enable it

### knowledge-graph
- Depends on SeaweedFS, Qdrant, and Ollama (cross-namespace FQDNs)
- These must be running in the cluster for the service to function
- No dev overlay exists — uses prod overlay as base_values

### todo
- Simplest service — single image, single deployment
- Persistence disabled in test (no git clone needed for UI testing)
- Good for smoke-testing the dev-deploy flow itself
