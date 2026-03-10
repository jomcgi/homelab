# ArgoCD App Colocation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Colocate ArgoCD Application definitions with their service code, replacing `overlays/` and `clusters/` with a single `projects/home-cluster/` auto-discovery root.

**Architecture:** Each service gets a `deploy/` directory containing its ArgoCD Application CR, cluster-specific values, and optional extras (imageupdater, alerts). Custom charts get renamed from `deploy/` to `chart/`, with a new `deploy/` for instance config. A convention-based script auto-generates the root kustomization by scanning for `deploy/kustomization.yaml` patterns.

**Tech Stack:** Kustomize, ArgoCD, Bash (generate script), Helm value files

---

## Context

**Current state:**

- 5 services have ArgoCD apps in `overlays/{dev,prod}/` with values split from their chart code
- `todo_app`, `blog_knowledge_graph` already have colocated deploy/ (chart + app mixed)
- `platform` and `agent_platform` are aggregators with top-level kustomization.yaml
- `clusters/homelab/kustomization.yaml` is the ArgoCD root, referencing overlays + projects
- `clusters/homelab/argocd/values.yaml` has cluster-specific ArgoCD config

**Services to migrate from overlays:**

| Service         | Overlay                         | Chart Location                             | Has ImageUpdater        | Has Alert                           |
| --------------- | ------------------------------- | ------------------------------------------ | ----------------------- | ----------------------------------- |
| grimoire        | `overlays/dev/grimoire/`        | `projects/grimoire/deploy/` (custom)       | Yes (in chart template) | No                                  |
| marine (ships)  | `overlays/dev/marine/`          | `projects/ships/deploy/` (custom)          | Yes (in chart template) | Yes (`marine-httpcheck-alert.yaml`) |
| oci-model-cache | `overlays/dev/oci-model-cache/` | `projects/operators/oci-model-cache/helm/` | Yes (in chart template) | No                                  |
| stargazer       | `overlays/dev/stargazer/`       | `projects/stargazer/deploy/` (custom)      | Yes (in chart template) | No                                  |
| trips           | `overlays/prod/trips/`          | `projects/trips/deploy/` (custom)          | No (api only)           | Yes (`img-httpcheck-alert.yaml`)    |

**Key path changes:**

- Image updater `writeBack.target` paths change from `helmvalues:../../overlays/dev/{service}/values.yaml` to `helmvalues:projects/{service}/deploy/values.yaml` (repo-root relative)
- Application `valueFiles` change from `../../../overlays/dev/{service}/values.yaml` to `../deploy/values.yaml` (source-path relative)
- `namePrefix: prod-` on trips, todo_app, blog_knowledge_graph, agent_platform will be dropped — ArgoCD app names change (e.g., `prod-trips` → `trips`). Brief reconciliation expected.

**Important:** The `deploy/` directories for grimoire, ships, stargazer, and trips currently ARE the Helm charts (contain Chart.yaml + templates/). These must be renamed to `chart/` first, then a new `deploy/` created for ArgoCD instance config. Any Bazel BUILD targets referencing these paths need updating.

---

### Task 1: Create auto-discovery script and home-cluster root

Create the convention-based script that generates `projects/home-cluster/kustomization.yaml` and integrate it into the format hook.

**Files:**

- Create: `bazel/images/generate-home-cluster.sh`
- Create: `projects/home-cluster/kustomization.yaml` (auto-generated)
- Modify: `bazel/tools/format/fast-format.sh` (add generate call)
- Modify: `bazel/tools/format/BUILD` (add sh_binary + multirun dep)
- Modify: `bazel/images/BUILD` (add sh_binary target)
- Modify: `bazel/images/validate-generate-scripts.sh` (add validation)
- Modify: `buildbuddy.yaml` (if validation script path changed)

**Step 1: Create the generate script**

Create `bazel/images/generate-home-cluster.sh`:

```bash
#!/usr/bin/env bash
# Auto-generate projects/home-cluster/kustomization.yaml from convention.
# Discovers all ArgoCD app deploy directories under projects/.
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

OUT_FILE="projects/home-cluster/kustomization.yaml"
mkdir -p "$(dirname "$OUT_FILE")"

# Find all deploy/kustomization.yaml files under projects/
# Exclude home-cluster itself and any nested deploy dirs (e.g., signoz dashboard-sidecar)
DEPLOY_PATHS=$(
	find projects -path "*/deploy/kustomization.yaml" \
		-not -path "projects/home-cluster/*" \
		-not -path "*/chart/*" \
		-not -path "*/templates/*" |
		sed 's|/kustomization.yaml$||' |
		LC_ALL=C sort
)

# Also find aggregator kustomizations (platform, agent_platform have top-level aggregators)
AGGREGATOR_PATHS=$(
	for dir in projects/platform projects/agent_platform; do
		if [ -f "$dir/kustomization.yaml" ]; then
			echo "$dir"
		fi
	done
)

# Combine and deduplicate — exclude deploy/ paths that fall under aggregator dirs
ALL_PATHS=""
for path in $AGGREGATOR_PATHS; do
	ALL_PATHS="${ALL_PATHS}${path}\n"
done
for path in $DEPLOY_PATHS; do
	# Skip if this path is under an aggregator directory
	skip=false
	for agg in $AGGREGATOR_PATHS; do
		case "$path" in "$agg"/*) skip=true ;; esac
	done
	if [ "$skip" = false ]; then
		ALL_PATHS="${ALL_PATHS}${path}\n"
	fi
done

SORTED_PATHS=$(echo -e "$ALL_PATHS" | grep -v '^$' | LC_ALL=C sort)

if [ -z "$SORTED_PATHS" ]; then
	echo "No deploy paths found"
	exit 0
fi

# Generate the kustomization file
{
	echo "# AUTO-GENERATED by bazel/images/generate-home-cluster.sh — DO NOT EDIT"
	echo "apiVersion: kustomize.config.k8s.io/v1beta1"
	echo "kind: Kustomization"
	echo ""
	echo "resources:"
	echo "$SORTED_PATHS" | while IFS= read -r path; do
		echo "  - ../../${path}"
	done
} >"$OUT_FILE"

echo "Generated $OUT_FILE with $(echo "$SORTED_PATHS" | wc -l | tr -d ' ') paths"
```

**Step 2: Make it executable**

Run: `chmod +x bazel/images/generate-home-cluster.sh`

**Step 3: Add sh_binary target to `bazel/images/BUILD`**

Add after the existing `sh_binary` targets in the generated header of `bazel/images/generate-push-all.sh`. Since `bazel/images/BUILD` is auto-generated, add the `generate-home-cluster` sh_binary to the header template in `generate-push-all.sh`.

Look at `bazel/images/generate-push-all.sh` — find the `HEADER` heredoc that writes `bazel/images/BUILD`. Add:

```starlark
sh_binary(
    name = "generate-home-cluster",
    srcs = ["generate-home-cluster.sh"],
    visibility = ["//:__subpackages__"],
)
```

**Step 4: Integrate into format hook**

In `bazel/tools/format/fast-format.sh`, find the lines that call `generate-push-all.sh` and add a parallel call:

```bash
./bazel/images/generate-home-cluster.sh 2>/dev/null &
```

Add this in BOTH the fast-path and full-format sections (same places where `generate-push-all.sh` is called).

Also update the `multirun` deps in `bazel/tools/format/BUILD` to include the new target:

```starlark
"//bazel/images:generate-home-cluster",
```

**Step 5: Create initial home-cluster directory**

Run: `mkdir -p projects/home-cluster`

**Step 6: Run format to generate the initial kustomization**

Run: `format`
Verify: `cat projects/home-cluster/kustomization.yaml` — should list all discovered deploy paths.

**Step 7: Commit**

```bash
git add bazel/images/generate-home-cluster.sh projects/home-cluster/
git commit -m "feat: add auto-discovery script for projects/home-cluster"
```

---

### Task 2: Migrate grimoire from overlay to colocated deploy/

Move the ArgoCD Application and overlay values from `overlays/dev/grimoire/` into `projects/grimoire/deploy/`, renaming the existing chart directory.

**Files:**

- Rename: `projects/grimoire/deploy/` → `projects/grimoire/chart/`
- Create: `projects/grimoire/deploy/application.yaml`
- Create: `projects/grimoire/deploy/values.yaml` (from overlay)
- Create: `projects/grimoire/deploy/kustomization.yaml`
- Delete: `overlays/dev/grimoire/`
- Modify: `overlays/dev/kustomization.yaml` (remove grimoire reference)

**Step 1: Rename deploy/ to chart/**

```bash
cd projects/grimoire
git mv deploy chart
```

This renames the Helm chart directory. All Bazel BUILD files referencing `projects/grimoire/deploy` will need updating — `format` (gazelle) handles this.

**Step 2: Create `projects/grimoire/deploy/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create `projects/grimoire/deploy/application.yaml`**

Copy from `overlays/dev/grimoire/application.yaml` and update paths:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: grimoire
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/grimoire/chart
    targetRevision: HEAD
    helm:
      releaseName: grimoire
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: grimoire
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jqPathExpressions:
        - .spec.template.metadata.annotations."otel.injected-by"
        - .spec.template.spec.containers[].env
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
```

Key changes from overlay version:

- `path:` → `projects/grimoire/chart` (was `projects/grimoire/deploy`)
- `valueFiles:` → `values.yaml` (chart defaults) + `../deploy/values.yaml` (cluster overrides, relative to chart path)

**Step 4: Create `projects/grimoire/deploy/values.yaml`**

Copy from `overlays/dev/grimoire/values.yaml` but update the image updater `writeBack.target`:

```yaml
# Cluster overrides for grimoire
# (copy entire content of overlays/dev/grimoire/values.yaml)
```

Change this line:

```yaml
target: helmvalues:../../overlays/dev/grimoire/values.yaml
```

To:

```yaml
target: helmvalues:projects/grimoire/deploy/values.yaml
```

**Step 5: Remove grimoire from overlay**

```bash
rm -rf overlays/dev/grimoire/
```

Edit `overlays/dev/kustomization.yaml` — remove the `- ./grimoire` line.

**Step 6: Run format**

Run: `format`
Verify: `projects/home-cluster/kustomization.yaml` now includes `projects/grimoire/deploy`.

**Step 7: Commit**

```bash
git add projects/grimoire/ overlays/
git commit -m "refactor(grimoire): colocate ArgoCD app with service code"
```

---

### Task 3: Migrate marine/ships from overlay to colocated deploy/

Same pattern as grimoire, plus the httpcheck alert. Note: the ArgoCD app is named "marine" but the project directory is "ships".

**Files:**

- Rename: `projects/ships/deploy/` → `projects/ships/chart/`
- Create: `projects/ships/deploy/application.yaml`
- Create: `projects/ships/deploy/values.yaml`
- Move: `overlays/dev/marine/marine-httpcheck-alert.yaml` → `projects/ships/deploy/marine-httpcheck-alert.yaml`
- Create: `projects/ships/deploy/kustomization.yaml`
- Delete: `overlays/dev/marine/`
- Modify: `overlays/dev/kustomization.yaml` (remove marine reference)

**Step 1: Rename deploy/ to chart/**

```bash
cd projects/ships
git mv deploy chart
```

**Step 2: Create `projects/ships/deploy/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - marine-httpcheck-alert.yaml
```

**Step 3: Create `projects/ships/deploy/application.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: marine
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/ships/chart
    targetRevision: HEAD
    helm:
      releaseName: marine
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: marine
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jqPathExpressions:
        - .spec.template.metadata.annotations."otel.injected-by"
        - .spec.template.spec.containers[].env
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
```

**Step 4: Create `projects/ships/deploy/values.yaml`**

Copy from `overlays/dev/marine/values.yaml`, update writeBack target:

```yaml
target: helmvalues:projects/ships/deploy/values.yaml
```

**Step 5: Move httpcheck alert**

```bash
cp overlays/dev/marine/marine-httpcheck-alert.yaml projects/ships/deploy/marine-httpcheck-alert.yaml
```

**Step 6: Remove marine from overlay**

```bash
rm -rf overlays/dev/marine/
```

Edit `overlays/dev/kustomization.yaml` — remove the `- ./marine` line.

**Step 7: Run format, commit**

Run: `format`

```bash
git add projects/ships/ overlays/
git commit -m "refactor(ships): colocate ArgoCD app with service code"
```

---

### Task 4: Migrate stargazer from overlay to colocated deploy/

Same pattern as grimoire.

**Files:**

- Rename: `projects/stargazer/deploy/` → `projects/stargazer/chart/`
- Create: `projects/stargazer/deploy/application.yaml`
- Create: `projects/stargazer/deploy/values.yaml`
- Create: `projects/stargazer/deploy/kustomization.yaml`
- Delete: `overlays/dev/stargazer/`
- Modify: `overlays/dev/kustomization.yaml` (remove stargazer reference)

**Step 1: Rename deploy/ to chart/**

```bash
cd projects/stargazer
git mv deploy chart
```

**Step 2: Create `projects/stargazer/deploy/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create `projects/stargazer/deploy/application.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: stargazer
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/stargazer/chart
    targetRevision: HEAD
    helm:
      releaseName: stargazer
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: stargazer
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jqPathExpressions:
        - .spec.template.metadata.annotations."otel.injected-by"
        - .spec.template.spec.containers[].env
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
```

**Step 4: Create `projects/stargazer/deploy/values.yaml`**

Copy from `overlays/dev/stargazer/values.yaml`, update writeBack target:

```yaml
target: helmvalues:projects/stargazer/deploy/values.yaml
```

**Step 5: Remove stargazer from overlay**

```bash
rm -rf overlays/dev/stargazer/
```

Edit `overlays/dev/kustomization.yaml` — remove the `- ./stargazer` line.

**Step 6: Run format, commit**

Run: `format`

```bash
git add projects/stargazer/ overlays/
git commit -m "refactor(stargazer): colocate ArgoCD app with service code"
```

---

### Task 5: Migrate trips from overlay to colocated deploy/

Trips is in `overlays/prod/` (with `namePrefix: prod-`). The app name will change from `prod-trips` to `trips`.

**Files:**

- Rename: `projects/trips/deploy/` → `projects/trips/chart/`
- Create: `projects/trips/deploy/application.yaml`
- Create: `projects/trips/deploy/values.yaml`
- Move: `overlays/prod/trips/img-httpcheck-alert.yaml` → `projects/trips/deploy/img-httpcheck-alert.yaml`
- Create: `projects/trips/deploy/kustomization.yaml`
- Delete: `overlays/prod/trips/`
- Modify: `overlays/prod/kustomization.yaml` (remove trips reference)

**Step 1: Rename deploy/ to chart/**

```bash
cd projects/trips
git mv deploy chart
```

**Step 2: Create `projects/trips/deploy/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - img-httpcheck-alert.yaml
```

**Step 3: Create `projects/trips/deploy/application.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: trips
  namespace: argocd
  labels:
    app.kubernetes.io/part-of: yukon-tracker
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/trips/chart
    targetRevision: HEAD
    helm:
      releaseName: trips
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: trips
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

Note: trips does not have `ignoreDifferences` or image updater — it's a simpler config.

**Step 4: Create `projects/trips/deploy/values.yaml`**

Copy from `overlays/prod/trips/values.yaml` (no writeBack target to update — trips doesn't use image updater in overlay):

```yaml
# Cluster overrides for trips

# Enable GHCR image pull secret for private images
imagePullSecret:
  enabled: true

api:
  enabled: true
  replicas: 2
  image:
    repository: ghcr.io/jomcgi/homelab/services/trips_api
    tag: main
  podAnnotations:
    instrumentation.opentelemetry.io/inject-python: "python"
```

**Step 5: Move httpcheck alert**

```bash
cp overlays/prod/trips/img-httpcheck-alert.yaml projects/trips/deploy/img-httpcheck-alert.yaml
```

**Step 6: Remove trips from overlay**

```bash
rm -rf overlays/prod/trips/
```

Edit `overlays/prod/kustomization.yaml` — remove the `- ./trips` line (this should leave the file with just the header and empty resources, or delete the file if trips was the only entry).

**Step 7: Run format, commit**

Run: `format`

```bash
git add projects/trips/ overlays/
git commit -m "refactor(trips): colocate ArgoCD app with service code"
```

---

### Task 6: Migrate oci-model-cache from overlay to colocated deploy/

The chart is at `projects/operators/oci-model-cache/helm/oci-model-cache-operator/` — no rename needed (it's not in `deploy/`). Just create a new `deploy/` directory.

**Files:**

- Create: `projects/operators/oci-model-cache/deploy/application.yaml`
- Create: `projects/operators/oci-model-cache/deploy/values.yaml`
- Create: `projects/operators/oci-model-cache/deploy/kustomization.yaml`
- Delete: `overlays/dev/oci-model-cache/`
- Modify: `overlays/dev/kustomization.yaml` (remove oci-model-cache reference)

**Step 1: Create `projects/operators/oci-model-cache/deploy/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 2: Create `projects/operators/oci-model-cache/deploy/application.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: oci-model-cache-operator
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: main
    path: projects/operators/oci-model-cache/helm/oci-model-cache-operator
    helm:
      valueFiles:
        - values.yaml
        - ../../../../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: oci-model-cache
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

Note the `valueFiles` path: from `projects/operators/oci-model-cache/helm/oci-model-cache-operator`, `../../../../deploy/values.yaml` resolves to `projects/operators/oci-model-cache/deploy/values.yaml`. Verify this is correct:

- `..` = `projects/operators/oci-model-cache/helm`
- `../..` = `projects/operators/oci-model-cache`
- Wait — that's only 2 levels up. The chart is 2 dirs deep: `helm/oci-model-cache-operator`.
- `../../..` = `projects/operators/oci-model-cache` ✓ No:
  - From `projects/operators/oci-model-cache/helm/oci-model-cache-operator`:
  - `..` = `helm`
  - `../..` = `oci-model-cache`
  - `../../deploy` = `oci-model-cache/deploy` ✓

So the correct path is `../../deploy/values.yaml`.

Corrected:

```yaml
helm:
  valueFiles:
    - values.yaml
    - ../../deploy/values.yaml
```

**Step 3: Create `projects/operators/oci-model-cache/deploy/values.yaml`**

Copy from `overlays/dev/oci-model-cache/values.yaml`, update writeBack target:

```yaml
target: helmvalues:projects/operators/oci-model-cache/deploy/values.yaml
```

(Was: `helmvalues:../../../../overlays/dev/oci-model-cache/values.yaml`)

**Step 4: Remove oci-model-cache from overlay**

```bash
rm -rf overlays/dev/oci-model-cache/
```

Edit `overlays/dev/kustomization.yaml` — remove the `- ./oci-model-cache` line.

**Step 5: Run format, commit**

Run: `format`

```bash
git add projects/operators/oci-model-cache/deploy/ overlays/
git commit -m "refactor(oci-model-cache): colocate ArgoCD app with operator code"
```

---

### Task 7: Integrate existing projects and remove namePrefix wrappers

`todo_app` and `blog_knowledge_graph` have top-level `kustomization.yaml` files with `namePrefix: prod-` that wrap their `deploy/` dirs. Remove these wrappers so the discovery script finds `deploy/kustomization.yaml` directly.

Also move `clusters/homelab/argocd/values.yaml` into the platform ArgoCD directory.

**Files:**

- Delete: `projects/todo_app/kustomization.yaml` (namePrefix wrapper)
- Delete: `projects/blog_knowledge_graph/kustomization.yaml` (namePrefix wrapper)
- Move: `clusters/homelab/argocd/values.yaml` → `projects/platform/argocd/values-cluster.yaml`
- Modify: `projects/platform/argocd/application.yaml` (update valueFiles path)
- Modify: `clusters/homelab/kustomization.yaml` (update references to use deploy/ directly)

**Step 1: Remove todo_app namePrefix wrapper**

```bash
rm projects/todo_app/kustomization.yaml
```

The discovery script will now find `projects/todo_app/deploy/kustomization.yaml` directly. The ArgoCD app name changes from `prod-todo` to `todo`. Verify `projects/todo_app/deploy/application.yaml` has `name: todo`.

**Step 2: Remove blog_knowledge_graph namePrefix wrapper**

```bash
rm projects/blog_knowledge_graph/kustomization.yaml
```

ArgoCD app name changes from `prod-knowledge-graph` to `knowledge-graph`.

**Step 3: Move ArgoCD cluster values**

```bash
git mv clusters/homelab/argocd/values.yaml projects/platform/argocd/values-cluster.yaml
```

**Step 4: Update ArgoCD application.yaml valueFiles**

Edit `projects/platform/argocd/application.yaml`. Change:

```yaml
valueFiles:
  - values.yaml
  - ../../../clusters/homelab/argocd/values.yaml
```

To:

```yaml
valueFiles:
  - values.yaml
  - values-cluster.yaml
```

**Step 5: Remove agent_platform namePrefix**

The `projects/agent_platform/kustomization.yaml` has `namePrefix: prod-`. Check if any agent_platform services have `prod-` prefixed names in the cluster. If so, removing the prefix will cause ArgoCD to recreate them.

Edit `projects/agent_platform/kustomization.yaml` — remove the `namePrefix: prod-` line.

**Step 6: Run format, commit**

Run: `format`

```bash
git add projects/ clusters/
git commit -m "refactor: remove namePrefix wrappers, move ArgoCD cluster values"
```

---

### Task 8: Switch ArgoCD root and delete old directories

Update ArgoCD to watch `projects/home-cluster/` and delete `overlays/` and `clusters/`.

**Files:**

- Modify: `projects/platform/argocd/application.yaml` or cluster values (update ArgoCD root path)
- Modify: `clusters/homelab/kustomization.yaml` (point to home-cluster)
- Delete: `overlays/` (should be empty after Tasks 2-6)
- Delete: `clusters/` (after verifying ArgoCD config moved)
- Modify: `CLAUDE.md` and `docs/` references

**Step 1: Verify overlays/ is empty**

Run: `find overlays -type f -name "*.yaml" | grep -v kustomization`
Expected: No results (all services migrated). The overlay kustomization files should have empty resource lists.

Run: `cat overlays/dev/kustomization.yaml` — should have no resources.
Run: `cat overlays/prod/kustomization.yaml` — should have no resources.

**Step 2: Update clusters/homelab/kustomization.yaml as transition**

Replace the entire content with:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../projects/home-cluster
```

This is a transitional step — ArgoCD currently watches `clusters/homelab/`, so we redirect it to the new root. After this is synced, we can update ArgoCD to watch `projects/home-cluster/` directly.

**Step 3: Run format, verify, commit**

Run: `format`
Verify: `cat projects/home-cluster/kustomization.yaml` lists all expected services.

```bash
git add clusters/ projects/home-cluster/
git commit -m "refactor: redirect ArgoCD root to projects/home-cluster"
```

**Step 4: Push, verify ArgoCD syncs correctly**

Push the branch and create a PR. After merge, verify all ArgoCD apps sync correctly:

- Use ArgoCD MCP tools to check app health
- Verify no apps are stuck in degraded/missing state

**Step 5: Delete overlays/ and clusters/ (separate commit after verification)**

Only after confirming ArgoCD is healthy:

```bash
git rm -rf overlays/
git rm -rf clusters/homelab/argocd/  # Already moved values in Task 7
git rm clusters/homelab/kustomization.yaml
```

**Step 6: Update documentation**

Update references in:

- Root `CLAUDE.md` — remove `overlays/` and `clusters/` from structure, add `projects/home-cluster/`
- Any docs referencing the old overlay paths

**Step 7: Commit**

```bash
git add .
git commit -m "chore: delete overlays/ and clusters/ directories"
```

---

## Risk Considerations

1. **App name changes** — Dropping `namePrefix: prod-` causes ArgoCD to see new apps (e.g., `trips` instead of `prod-trips`) and delete old ones. The new apps auto-create immediately via `syncPolicy.automated`. Expect ~30s of reconciliation per affected app.

2. **Image Updater writeBack paths** — If any in-flight image update commits reference old paths, they'll fail. Image Updater will retry with the new path on next cycle.

3. **Bazel BUILD references** — Renaming `deploy/` to `chart/` changes Bazel package paths. The `format` hook (gazelle) regenerates BUILD files, but verify `helm_chart` and `helm_push` targets still resolve.

4. **Gradual rollout** — Each task is independently deployable. If one service migration has issues, others are unaffected. The old `clusters/homelab/kustomization.yaml` continues to work until Task 8.
