# N8N Workflow GitOps Management

This chart provides GitOps-based workflow management for n8n using a Go-based syncer with OpenTelemetry observability.

## Architecture

```
Git Push
   ↓
ArgoCD Sync (ConfigMap changes)
   ↓
PostSync Hook: workflow-sync Job
   ↓
Go Syncer (with OpenTelemetry)
   ├─> Structured JSON logs → SigNoz
   ├─> Distributed traces → SigNoz
   ├─> Metrics → Prometheus
   └─> Sync workflows to n8n API

              +

CronJob: Every 30min (drift detection)
   ↓
Same Go Syncer
   ├─> Check for manual workflow changes
   └─> Re-sync from Git (source of truth)
```

## How It Works

### 1. Workflows as ConfigMaps
Each workflow is stored as a Kubernetes ConfigMap containing the workflow JSON:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: n8n-workflow-my-workflow
  namespace: n8n
data:
  my-workflow.json: |
    {"name": "My Workflow", "nodes": [...]}
```

### 2. ArgoCD PostSync Hook
After ArgoCD syncs ConfigMap changes, a Job automatically runs to sync workflows to n8n. This ensures:
- **Immediate sync** on Git push
- **No wasted runs** (only runs when workflows change)
- **GitOps-native** (integrates with ArgoCD lifecycle)

### 3. CronJob Drift Detection
A CronJob runs every 30 minutes to:
- **Detect manual changes** in n8n UI
- **Re-sync from Git** (Git is the source of truth)
- **Emit drift metrics** for alerting

### 4. Name-Based Matching
Workflows are matched by name with a `[git-managed]` suffix:
- **In Git**: `"name": "Joe Phone Tracker"`
- **In n8n**: `Joe Phone Tracker [git-managed]`
- **Tags**: Automatically tagged with `gitops-managed`

This allows **both** manual and GitOps workflows to coexist.

## Observability

The Go syncer emits comprehensive telemetry:

### Traces
Distributed traces show the complete sync flow in SigNoz:
```
sync.Sync
├─ sync.waitForN8N
├─ sync.loadWorkflows
├─ n8n.ListWorkflows
├─ sync.syncWorkflow (per workflow)
│  ├─ n8n.CreateWorkflow OR
│  └─ n8n.UpdateWorkflow
└─ Complete
```

### Metrics
Prometheus metrics for alerting:
- `n8n_workflows_synced_total` - Total workflows synced
- `n8n_workflows_created_total` - Workflows created
- `n8n_workflows_updated_total` - Workflows updated
- `n8n_workflows_failed_total` - Workflows that failed to sync
- `n8n_sync_duration_seconds` - Sync operation duration

### Logs
Structured JSON logs for easy querying in SigNoz:
```json
{
  "level": "info",
  "message": "workflow sync completed",
  "total": 5,
  "created": 2,
  "updated": 3,
  "failed": 0,
  "duration_seconds": 1.234
}
```

## Configuration

### Base Chart (`charts/n8n/values.yaml`)

```yaml
workflowSync:
  enabled: false
  managedSuffix: " [git-managed]"
  managedTag: "gitops-managed"
  logLevel: "info"

  image:
    repository: ghcr.io/jomcgi/homelab/n8n-workflow-syncer
    tag: "latest"
    pullPolicy: IfNotPresent

  apiKeySecret:
    name: "n8n-api-key"
    key: "api-key"

  workflowConfigMaps: []

  telemetry:
    enabled: false
    otlpEndpoint: ""

  driftDetection:
    enabled: false
    schedule: "*/30 * * * *"

  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "500m"
      memory: "256Mi"
```

### Production Override (`overlays/prod/n8n/values.yaml`)

```yaml
workflowSync:
  enabled: true
  workflowConfigMaps:
    - n8n-workflow-joe-phone-tracker
    - n8n-workflow-other-workflow

  telemetry:
    enabled: true
    otlpEndpoint: "signoz-otel-collector.signoz.svc.cluster.local:4317"

  driftDetection:
    enabled: true
```

## Adding a New Workflow

### 1. Export from n8n UI
Download workflow as JSON from n8n (click "..." → "Download").

### 2. Clean Instance Data
```bash
cat downloaded-workflow.json | jq 'del(.id) |
  walk(if type == "object" then del(.webhookId) else . end) |
  del(.meta.instanceId)' > cleaned-workflow.json
```

### 3. Create ConfigMap
```bash
cat > overlays/prod/n8n/workflows/my-workflow.yaml <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: n8n-workflow-my-workflow
  namespace: n8n
  labels:
    app.kubernetes.io/name: n8n
    app.kubernetes.io/component: workflow
data:
  my-workflow.json: |
$(cat cleaned-workflow.json | sed 's/^/    /')
EOF
```

### 4. Add to Kustomization
```bash
# Edit overlays/prod/n8n/kustomization.yaml
resources:
  - ./workflows/my-workflow.yaml
```

### 5. Add to Helm Values
```bash
# Edit overlays/prod/n8n/values.yaml
workflowSync:
  workflowConfigMaps:
    - n8n-workflow-joe-phone-tracker
    - n8n-workflow-my-workflow  # Add this
```

### 6. Commit and Push
```bash
git add overlays/prod/n8n/
git commit -m "feat(n8n): add my-workflow"
git push
```

ArgoCD will automatically:
1. Sync the ConfigMap
2. Trigger PostSync hook
3. Run workflow syncer
4. Import workflow to n8n

## Updating a Workflow

1. Edit the JSON in the ConfigMap
2. Commit and push
3. ArgoCD syncs and triggers PostSync hook
4. Workflow automatically updates in n8n

**No pod restart required!** The PostSync Job handles the update.

## Setup Requirements

### 1. Create 1Password Item

The n8n workflow sync requires a 1Password item at `vaults/k8s-homelab/items/n8n-workflow-sync` with the following fields:

#### Required Fields:

1. **api-key** (or "API Key"):
   - **IMPORTANT**: Field must be named exactly `api-key` or `API Key` (NOT `n8n-api-key`)
   - Type: Password or Text
   - Value: Your n8n API key (generated from n8n UI)
   - Note: "API Key" will be transformed to `api-key` in the Kubernetes secret
   - The application expects the secret key to be `api-key`, so the 1Password field name matters!

2. **.dockerconfigjson**:
   - Type: File
   - Value: Docker config JSON for GitHub Container Registry authentication
   - Format:
     ```json
     {
       "auths": {
         "ghcr.io": {
           "auth": "BASE64_ENCODED_USERNAME:TOKEN"
         }
       }
     }
     ```
   - Used by: imagePullSecrets to pull the private workflow syncer image

#### Generate n8n API Key

```bash
# 1. Open n8n UI at n8n.jomcgi.dev
# 2. Go to Settings > n8n API
# 3. Click "Create an API key"
# 4. Copy the generated key
# 5. Add it to the 1Password item as "API Key" or "api-key" field
```

#### Field Name Transformation Rules

The 1Password operator transforms field names to valid Kubernetes secret keys:
- Whitespace → dash (`-`)
- Lowercase conversion
- Invalid characters removed

Examples:
- "API Key" → "api-key"
- "api-key" → "api-key"
- "n8n API Key" → "n8n-api-key"

### 2. Verify 1Password Operator Created Secrets

The secrets are automatically created by the 1Password operator from the OnePasswordItem CRDs:

```bash
# Check if secrets exist
kubectl get onepassworditems -n n8n
kubectl get secrets -n n8n n8n-api-key
kubectl get secrets -n n8n ghcr-pull-secret

# Verify secret keys
kubectl get secret n8n-api-key -n n8n -o jsonpath='{.data}' | jq 'keys'
# Should output: ["api-key"]
```

### 3. Verify Sync
After ArgoCD syncs:

```bash
# Check PostSync Job logs
kubectl logs -n n8n job/n8n-workflow-sync-<revision> -f

# Expected output:
# {"level":"info","message":"starting workflow sync"}
# {"level":"info","message":"n8n is ready"}
# {"level":"info","message":"found workflows to sync","count":1}
# {"level":"info","message":"created workflow","name":"Joe Phone Tracker [git-managed]","id":"123"}
# {"level":"info","message":"workflow sync completed","total":1,"created":1,"updated":0,"failed":0}
```

## Drift Detection

The CronJob runs every 30 minutes to reconcile state:

```bash
# Check CronJob status
kubectl get cronjob -n n8n n8n-workflow-sync

# Check recent Job runs
kubectl get jobs -n n8n -l app.kubernetes.io/component=workflow-sync

# View logs from latest run
kubectl logs -n n8n -l app.kubernetes.io/component=workflow-sync --tail=100
```

If someone manually edits a workflow in the n8n UI, the CronJob will:
1. Detect the change
2. Re-sync from Git (source of truth)
3. Overwrite the manual change
4. Emit metrics for alerting

## Troubleshooting

### Error: secret "n8n-api-key" not found

This error occurs when the 1Password operator hasn't created the secret. Check:

1. **Verify 1Password item exists**:
   - Path: `vaults/k8s-homelab/items/n8n-workflow-sync`
   - Must contain field named `api-key` or `API Key` (NOT `n8n-api-key`)
   - Must contain file field `.dockerconfigjson`

2. **Check 1Password operator is running**:
   ```bash
   kubectl get pods -n onepassword-operator
   ```

3. **Check OnePasswordItem status**:
   ```bash
   kubectl get onepassworditems -n n8n
   kubectl describe onepassworditem n8n-api-key -n n8n
   ```
   Look for errors in the Events section.

4. **Verify secret was created**:
   ```bash
   kubectl get secret n8n-api-key -n n8n
   kubectl get secret n8n-api-key -n n8n -o jsonpath='{.data}' | jq 'keys'
   ```
   Should output: `["api-key"]`

5. **Common fix**: Rename the 1Password field from `n8n-api-key` to `api-key` or `API Key`

### PostSync Job Failed
```bash
# Check job status
kubectl describe job -n n8n n8n-workflow-sync-<revision>

# View logs
kubectl logs -n n8n job/n8n-workflow-sync-<revision>
```

Common issues:
- **n8n not ready**: Job waits up to 2 minutes for n8n to be healthy
- **Invalid API key**: Check secret exists and is correct
- **Invalid workflow JSON**: Validate JSON with `jq`

### Workflow Not Appearing in n8n
1. Check ConfigMap exists: `kubectl get cm -n n8n | grep workflow`
2. Check it's listed in `workflowConfigMaps`
3. Check PostSync Job logs for errors
4. Verify workflow JSON is valid

### Traces Not in SigNoz
1. Verify `telemetry.enabled: true`
2. Check OTLP endpoint is correct
3. Ensure SigNoz collector is running
4. Check syncer logs for telemetry errors

## Benefits

✅ **Immediate sync** - PostSync hook triggers on Git push
✅ **Full observability** - Traces, metrics, and logs in SigNoz
✅ **Drift detection** - Automatic reconciliation every 30min
✅ **GitOps-native** - Integrates with ArgoCD lifecycle
✅ **Type-safe** - Go syncer with proper error handling
✅ **Testable** - Unit tests for sync logic (future)
✅ **Performant** - ~20MB distroless container
✅ **Secure** - Runs as non-root, read-only filesystem

## Desired State / Future Enhancements

### Kubernetes Operator (Long-term Vision)

While the current PostSync Hook + CronJob approach works well for small-scale deployments, a **Kubernetes Operator** would provide a more robust, cloud-native solution for managing n8n workflows at scale.

#### Why an Operator?

**Current Limitations:**
- PostSync hooks are one-shot (no continuous reconciliation)
- CronJob drift detection has eventual consistency delay
- No status reporting on workflow sync state
- Limited lifecycle management (create/update only, no delete)
- ConfigMaps don't expose sync status

**Operator Benefits:**
- **Immediate reconciliation** - Controller watches CRDs and syncs instantly
- **Status reporting** - See sync state in `kubectl get n8nworkflows`
- **Event-driven** - No polling, reacts to changes immediately
- **Proper deletions** - Can delete workflows from n8n when CRD is removed
- **Conflict resolution** - Handle manual UI changes with configurable policies
- **Multi-tenancy** - Manage workflows across multiple n8n instances
- **Validation webhooks** - Validate workflow JSON before applying
- **Finalizers** - Ensure cleanup before workflow deletion

#### Proposed CRD Design

```yaml
apiVersion: n8n.jomcgi.dev/v1alpha1
kind: N8NWorkflow
metadata:
  name: joe-phone-tracker
  namespace: n8n
spec:
  # Target n8n instance
  n8nRef:
    name: n8n
    namespace: n8n

  # Workflow definition (inline or configMapRef)
  workflow:
    name: "Joe Phone Tracker"
    nodes:
      - parameters: {...}
        type: "n8n-nodes-base.webhook"
        # ...
    connections: {...}

  # OR reference a ConfigMap
  # workflowConfigMapRef:
  #   name: n8n-workflow-joe-phone-tracker
  #   key: joe-phone-tracker.json

  # Conflict resolution policy
  conflictPolicy: GitWins  # or: ManualWins, Fail

  # Managed metadata
  managedSuffix: " [git-managed]"
  tags:
    - gitops-managed

status:
  # Sync status
  syncedToN8N: true
  workflowID: "123"
  lastSyncTime: "2025-01-15T10:00:00Z"

  # Drift detection
  driftDetected: false
  lastDriftCheckTime: "2025-01-15T10:15:00Z"

  # Conditions
  conditions:
    - type: Synced
      status: "True"
      reason: "WorkflowSynced"
      message: "Workflow successfully synced to n8n"
      lastTransitionTime: "2025-01-15T10:00:00Z"
```

#### Controller Architecture

```
Controller Manager
├─ N8NWorkflow Controller
│  ├─ Watch: N8NWorkflow CRDs
│  ├─ Watch: ConfigMaps (for workflowConfigMapRef)
│  └─ Reconcile Loop:
│     1. Get workflow from spec or ConfigMap
│     2. Check n8n for existing workflow
│     3. Create/Update/Delete in n8n
│     4. Update status with sync result
│     5. Emit events for observability
│     6. Requeue for periodic drift detection
│
├─ Drift Detector
│  ├─ Periodic checks (every 5 min)
│  ├─ Compare n8n state vs CRD spec
│  ├─ Apply conflictPolicy
│  └─ Update status.driftDetected
│
└─ Webhooks
   ├─ Validation: Validate workflow JSON
   └─ Mutation: Add managed suffix and tags
```

#### Implementation Path

**Phase 1: Basic Operator** (MVP)
- CRD definition with inline workflow spec
- Controller with basic create/update logic
- Status reporting
- Replace PostSync hook

**Phase 2: Advanced Features**
- ConfigMap reference support
- Drift detection and conflict policies
- Validation/mutation webhooks
- Event emission

**Phase 3: Multi-Instance & Scale**
- Manage multiple n8n instances
- Leader election for HA controller
- Workflow templating (Kustomize-style)
- Batch operations

**Phase 4: Production Hardening**
- Comprehensive unit/integration tests
- Metrics and tracing for controller
- Prometheus ServiceMonitor
- OLM bundle for easy installation

#### Migration Strategy

The operator can coexist with the current approach:

1. **Deploy operator** alongside PostSync/CronJob
2. **Gradually migrate** workflows from ConfigMaps to CRDs
3. **Disable** PostSync hook once all workflows migrated
4. **Remove** CronJob (no longer needed)

This allows zero-downtime migration and easy rollback if needed.

#### When to Build This?

**Build the operator when:**
- Managing 10+ workflows
- Need immediate drift correction
- Want proper status reporting
- Require workflow lifecycle management (delete)
- Multiple n8n instances
- Team wants CRD-based workflows

**Stick with current approach if:**
- < 10 workflows
- 30min drift detection is acceptable
- PostSync hook + CronJob is simple enough
- Limited development time

#### Recommended Tooling

- **Kubebuilder** or **Operator SDK** - Scaffold operator boilerplate
- **controller-runtime** - Kubernetes controller framework
- **kustomize** - CRD management
- **envtest** - Integration testing
- **kind** - Local Kubernetes for testing

#### Estimated Effort

- **Basic operator (Phase 1)**: ~2-3 days
- **Advanced features (Phase 2)**: ~3-4 days
- **Production hardening (Phase 3-4)**: ~5-7 days
- **Total**: ~2-3 weeks for production-ready operator

---

### Other Future Enhancements

**Workflow Validation:**
- Pre-commit hooks to validate workflow JSON
- CI/CD checks for workflow syntax
- Webhook validation before applying

**Workflow Templating:**
- Kustomize overlays for per-environment workflows
- Helm subchart for reusable workflow patterns
- Workflow composition (shared subflows)

**Bidirectional Sync:**
- Export workflows from n8n back to Git
- Pull Request creation for UI-created workflows
- Automated GitOps for UI changes

**Advanced Observability:**
- Workflow execution tracing
- Per-workflow metrics (execution count, duration, failures)
- Dashboards for workflow health

**Testing:**
- Workflow dry-run validation
- Integration tests for workflow logic
- Snapshot testing for workflow changes

---

## Current Limitations

⚠️ **PostSync only** - Workflows sync after ArgoCD syncs (not continuous)
⚠️ **Manual deletion** - Deleting from Git doesn't delete from n8n
⚠️ **Eventual consistency** - Drift detection up to 30min delay
⚠️ **No status reporting** - Can't see sync status in Kubernetes

These limitations will be addressed by the Kubernetes Operator in the future.

## Contributing

The workflow syncer source code lives in `charts/n8n/syncer/`:
- `internal/n8n/` - N8N API client
- `internal/sync/` - Sync logic
- `internal/telemetry/` - OpenTelemetry setup
- `main.go` - CLI entry point
- `Dockerfile` - Multi-stage build

Pull requests welcome! 🚀
