# Testing the Helm Gazelle Extension

## Prerequisites
- Bazel installed
- Helm added to multitool (already configured)
- ArgoCD applications in `overlays/*/

## Manual Testing

### 1. Test helm tool availability
```bash
bazel run @multitool//tools/helm -- version
```

### 2. Create a manual test BUILD file

Create `overlays/dev/n8n-obsidian-api/BUILD` with:

```starlark
load("//tools/helm:defs.bzl", "helm_render", "helm_diff_script")

helm_render(
    name = "render",
    chart = "//charts/n8n-obsidian-api:Chart.yaml",
    release_name = "n8n-obsidian-api",
    namespace = "n8n",
    values = [
        "//charts/n8n-obsidian-api:values.yaml",
        "values.yaml",
    ],
)

helm_diff_script(
    name = "diff",
    rendered = ":render",
    namespace = "n8n",
    kubectl_context = "homelab",  # Or your cluster context
)
```

### 3. Test the render rule
```bash
bazel run //overlays/dev/n8n-obsidian-api:render
```

This should output the rendered Kubernetes manifests.

### 4. Test the diff rule (requires cluster access)
```bash
bazel run //overlays/dev/n8n-obsidian-api:diff
```

This will compare the rendered manifests with what's deployed in the cluster.

## Gazelle Extension Testing

### 1. Run gazelle to generate BUILD files
```bash
bazel run //:gazelle
```

This should automatically discover `application.yaml` files and generate BUILD files with `helm_render` and `helm_diff_script` rules.

### 2. Verify generated BUILD files
Check that BUILD files were created in:
- `overlays/cluster-critical/argocd/`
- `overlays/prod/n8n/`
- `overlays/dev/n8n-obsidian-api/`

### 3. Enable diff generation for specific overlays

Add this directive to `overlays/prod/kustomization.yaml`:

```yaml
# gazelle:argocd_generate_diff true
# gazelle:kubectl_context homelab
```

Then re-run gazelle and verify diff rules are generated.

## Troubleshooting

### Issue: "helm: command not found"
The multitool helm binary might not be properly configured. Verify with:
```bash
bazel query @multitool//tools/helm
```

### Issue: "Cannot find Chart.yaml"
Check that the `chart` attribute points to the correct Chart.yaml file:
```bash
ls -la charts/n8n-obsidian-api/Chart.yaml
```

### Issue: "kubectl: command not found" when running diff
The diff script requires kubectl to be installed and in PATH. Install it or skip diff testing.

### Issue: Gazelle doesn't generate BUILD files
Check that:
1. The directory contains an `application.yaml` file
2. The file is a valid ArgoCD Application
3. The directory isn't excluded by `.bazelignore`

## Expected Output

### Successful render:
```
$ bazel run //overlays/dev/n8n-obsidian-api:render
INFO: Rendering Helm chart n8n-obsidian-api
apiVersion: v1
kind: Service
metadata:
  name: n8n-obsidian-api
...
```

### Successful diff:
```
$ bazel run //overlays/dev/n8n-obsidian-api:diff
Comparing rendered manifests with cluster state...
Namespace: n8n
Context: homelab

diff -u -N /tmp/LIVE-123/v1.Service.n8n.n8n-obsidian-api /tmp/MERGED-456/v1.Service.n8n.n8n-obsidian-api
...

Diff complete. Exit code 0 = no changes, 1 = changes detected
```
