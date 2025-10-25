# N8N Workflow GitOps Management

This directory contains n8n workflows managed as Kubernetes ConfigMaps, automatically synced to n8n via an initContainer.

## How It Works

1. **Workflows as ConfigMaps**: Each workflow is stored as a ConfigMap containing the workflow JSON
2. **InitContainer Sync**: On pod start, an initContainer reads all workflow ConfigMaps and syncs them to n8n via the API
3. **Name-Based Matching**: Workflows are matched by name with a `[git-managed]` suffix to distinguish them from UI-created workflows
4. **Tagged for Identification**: All managed workflows are tagged with `gitops-managed`

## Workflow Naming Convention

- **In Git**: `"name": "Joe Phone Tracker"`
- **In n8n UI**: `Joe Phone Tracker [git-managed]`
- **Tags**: Automatically tagged with `gitops-managed`

This makes it crystal clear which workflows are managed by Git and which are created manually.

## Adding a New Workflow

### Option 1: Export Existing Workflow from n8n

1. **Export from UI**: In n8n, open the workflow and click "..." → "Download"
2. **Clean the JSON**: Remove instance-specific fields:
   ```bash
   # Remove id, webhookId, instanceId
   cat downloaded-workflow.json | jq 'del(.id) |
     walk(if type == "object" then del(.webhookId) else . end) |
     del(.meta.instanceId)' > cleaned-workflow.json
   ```

3. **Create ConfigMap**:
   ```bash
   # Replace 'my-workflow' with your workflow name (slugified)
   cat > my-workflow.yaml <<EOF
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: n8n-workflow-my-workflow
     namespace: n8n
     labels:
       app.kubernetes.io/name: n8n
       app.kubernetes.io/component: workflow
       workflow-sync: "enabled"
   data:
     my-workflow.json: |
   $(cat cleaned-workflow.json | sed 's/^/    /')
   EOF
   ```

4. **Add to Kustomization**:
   ```bash
   # Edit overlays/prod/n8n/kustomization.yaml
   # Add your workflow under resources:
   # - ./workflows/my-workflow.yaml
   ```

5. **Add to Helm Values**:
   ```bash
   # Edit overlays/prod/n8n/values.yaml
   # Add your workflow ConfigMap to the projected volume:
   # - configMap:
   #     name: n8n-workflow-my-workflow
   ```

6. **Commit and Push**: ArgoCD will sync the changes, and the next pod restart will import the workflow

### Option 2: Create Workflow from Scratch

1. Create the workflow JSON following n8n's structure (see `joe-phone-tracker.yaml` for an example)
2. Follow steps 3-6 from Option 1

## Updating a Workflow

1. **Update the ConfigMap**: Edit the workflow JSON in the corresponding YAML file
2. **Commit and Push**: ArgoCD syncs the ConfigMap change
3. **Restart n8n Pod**: The initContainer will update the workflow on startup
   ```bash
   kubectl rollout restart deployment/n8n -n n8n
   ```

## Deleting a Workflow

1. **Remove from Git**:
   - Delete the workflow YAML file
   - Remove from `kustomization.yaml`
   - Remove from `values.yaml` projected volume sources
2. **Manual cleanup in n8n**: Delete the workflow from the n8n UI (or via API)

⚠️ **Note**: Deleting from Git does NOT automatically delete from n8n. This is by design to prevent accidental data loss.

## Setup Requirements

### 1. Generate n8n API Key

```bash
# 1. Open n8n UI at n8n.jomcgi.dev
# 2. Go to Settings > n8n API
# 3. Click "Create an API key"
# 4. Copy the generated API key
```

### 2. Create Kubernetes Secret

```bash
kubectl create secret generic n8n-api-key \
  --from-literal=api-key=YOUR_API_KEY_HERE \
  --namespace=n8n
```

### 3. Verify Setup

After ArgoCD syncs and the pod restarts:

```bash
# Check initContainer logs
kubectl logs -n n8n deployment/n8n -c workflow-sync

# Expected output:
# =========================================
# n8n Workflow GitOps Sync
# =========================================
# Found 1 workflow file(s) to process
# [1/1] Processing: joe-phone-tracker.json
#   Original name: Joe Phone Tracker
#   Managed name: Joe Phone Tracker [git-managed]
#   → Creating new workflow
#   ✓ Successfully created workflow
# ✓ All workflows synced successfully!
```

## Troubleshooting

### InitContainer fails with "n8n failed to become ready"
- Check that n8n is starting correctly: `kubectl logs -n n8n deployment/n8n`
- Verify the main container is healthy before the initContainer runs

### Workflow not appearing in n8n
- Check initContainer logs: `kubectl logs -n n8n deployment/n8n -c workflow-sync`
- Verify the API key secret exists: `kubectl get secret n8n-api-key -n n8n`
- Ensure the workflow JSON is valid: use `jq` to validate

### Workflow created with different ID than expected
- This is expected! n8n assigns IDs automatically
- Updates are matched by name, not ID
- The `[git-managed]` suffix ensures unique identification

### Multiple workflows with the same name
- Only workflows with the `[git-managed]` suffix are managed
- Manually created workflows (without suffix) are left untouched
- You can have both "My Workflow" (manual) and "My Workflow [git-managed]" (GitOps)

## Directory Structure

```
overlays/prod/n8n/
├── workflows/
│   ├── README.md                    # This file
│   ├── joe-phone-tracker.yaml       # Example workflow
│   └── my-other-workflow.yaml       # Your workflows here
├── application.yaml                 # ArgoCD application
├── kustomization.yaml              # Lists workflow resources
└── values.yaml                      # Helm values with initContainer config
```

## Workflow JSON Structure

A minimal n8n workflow requires:

```json
{
  "name": "My Workflow",
  "nodes": [
    {
      "parameters": {},
      "type": "n8n-nodes-base.start",
      "typeVersion": 1,
      "position": [0, 0],
      "id": "unique-id",
      "name": "Start"
    }
  ],
  "connections": {},
  "pinData": {}
}
```

See `joe-phone-tracker.yaml` for a complete example.

## Benefits of GitOps Workflow Management

✅ **Version Control**: Full Git history of workflow changes
✅ **Code Review**: PR-based workflow changes
✅ **Disaster Recovery**: Workflows reconstructed from Git
✅ **Environment Parity**: Same workflows across dev/prod
✅ **Audit Trail**: Who changed what and when
✅ **Rollback**: Revert to previous workflow versions
✅ **Documentation**: Workflows live next to code

## Limitations

⚠️ **Pod Restart Required**: Workflow changes require pod restart
⚠️ **One-Way Sync**: Changes in n8n UI won't sync back to Git
⚠️ **Manual Deletion**: Removing from Git doesn't delete from n8n
⚠️ **Credential Separate**: Workflow credentials must be configured separately

## Future Improvements

Ideas for enhancing this system:

- **CronJob sync**: Periodic sync instead of only on pod restart
- **Bidirectional sync**: Export workflows from n8n back to Git
- **Validation**: Pre-commit hooks to validate workflow JSON
- **CRD operator**: Custom N8NWorkflow resource type
- **Automated testing**: CI/CD workflow validation
