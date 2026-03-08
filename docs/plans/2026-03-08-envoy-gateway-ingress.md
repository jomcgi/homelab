# Envoy Gateway Ingress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Envoy Gateway with a `cloudflare-ingress` Gateway and wire the tunnel's catch-all to it, so future route migrations only require adding HTTPRoutes.

**Architecture:** Envoy Gateway control plane in `envoy-gateway-system` (cluster-critical), a `cloudflare-ingress` GatewayClass/Gateway/EnvoyProxy chart in prod, and a one-line tunnel catch-all change. No routes migrated -- Envoy returns 404 for unmatched traffic.

**Tech Stack:** Helm charts, Kustomize overlays, ArgoCD Applications, Gateway API v1, Envoy Gateway v1.3.2

**Design doc:** `docs/plans/2026-03-08-envoy-gateway-ingress-design.md`

**Worktree:** `/tmp/claude-worktrees/envoy-gateway-ingress` (branch: `feat/envoy-gateway-ingress`)

---

### Task 1: Envoy Gateway wrapper chart

Create the Helm chart that wraps the upstream `gateway-helm` chart.

**Files:**

- Create: `charts/envoy-gateway/Chart.yaml`
- Create: `charts/envoy-gateway/values.yaml`
- Create: `charts/envoy-gateway/charts/gateway-helm-v1.3.2.tgz` (vendored dependency)

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: envoy-gateway
description: Envoy Gateway - Gateway API implementation for Kubernetes ingress routing
type: application
version: 1.0.0
appVersion: "v1.3.2"

dependencies:
  - name: gateway-helm
    repository: oci://docker.io/envoyproxy
    version: v1.3.2

annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

Base values for the upstream chart. Resource limits are defaults; overlay overrides them.

```yaml
gateway-helm:
  deployment:
    envoyGateway:
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi

  config:
    envoyGateway:
      provider:
        type: Kubernetes
```

**Step 3: Vendor the upstream chart dependency**

```bash
mkdir -p charts/envoy-gateway/charts
helm pull oci://docker.io/envoyproxy/gateway-helm --version v1.3.2 --destination charts/envoy-gateway/charts/
```

**Step 4: Verify template renders**

```bash
helm template envoy-gateway charts/envoy-gateway/ --namespace envoy-gateway-system
```

Expected: Renders ServiceAccount, ConfigMap, Deployment, CRDs, etc. No errors.

**Step 5: Commit**

```bash
git add charts/envoy-gateway/
git commit -m "feat(envoy-gateway): add wrapper chart for upstream gateway-helm v1.3.2"
```

---

### Task 2: Envoy Gateway ArgoCD overlay (cluster-critical)

**Files:**

- Create: `overlays/cluster-critical/envoy/application.yaml`
- Create: `overlays/cluster-critical/envoy/kustomization.yaml`
- Create: `overlays/cluster-critical/envoy/values.yaml`
- Create: `overlays/cluster-critical/envoy/BUILD`
- Modify: `overlays/cluster-critical/kustomization.yaml`

**Step 1: Create application.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: envoy-gateway
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: charts/envoy-gateway
    helm:
      valueFiles:
        - values.yaml
        - ../../overlays/cluster-critical/envoy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: envoy-gateway-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    managedNamespaceMetadata:
      annotations:
        # Disable Linkerd sidecar injection -- iptables transparent proxy rules
        # interfere with QUIC/UDP conntrack flows (same issue seen with cloudflare-tunnel).
        linkerd.io/inject: disabled
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

**Step 2: Create kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create values.yaml**

```yaml
# Envoy Gateway cluster-specific overrides

gateway-helm:
  deployment:
    envoyGateway:
      # Keep control plane alive under node pressure
      priorityClassName: system-cluster-critical
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi
      securityContext:
        readOnlyRootFilesystem: true

  config:
    envoyGateway:
      provider:
        type: Kubernetes
```

Note: The `envoyDeployment` (data-plane proxy) resource limits are NOT set here -- they are controlled per-GatewayClass via the `EnvoyProxy` CRD in the `cloudflare-ingress` chart. This keeps control-plane config separate from per-gateway data-plane config.

**Step 4: Create BUILD**

```starlark
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "envoy-gateway",
    chart = "charts/envoy-gateway",
    chart_files = "//charts/envoy-gateway:chart",
    namespace = "envoy-gateway-system",
    release_name = "envoy-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/envoy-gateway:values.yaml",
        "values.yaml",
    ],
)
```

**Step 5: Add chart BUILD file**

Create `charts/envoy-gateway/BUILD`:

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/cluster-critical/envoy:__pkg__"],
)
```

`lint = False` because the chart wraps an upstream dependency -- linting the vendored `.tgz` contents fails.

**Step 6: Add envoy to cluster-critical kustomization**

Modify `overlays/cluster-critical/kustomization.yaml` -- add `./envoy` after `./opentelemetry-operator` and before `./linkerd`:

```yaml
- ./opentelemetry-operator
- ./envoy # Installs Gateway API CRDs; must be before linkerd
- ./linkerd
```

**Step 7: Run helm template to verify**

```bash
helm template envoy-gateway charts/envoy-gateway/ -f overlays/cluster-critical/envoy/values.yaml --namespace envoy-gateway-system | head -20
```

Expected: Renders successfully with `priorityClassName: system-cluster-critical` and `readOnlyRootFilesystem: true`.

**Step 8: Commit**

```bash
git add overlays/cluster-critical/envoy/ charts/envoy-gateway/BUILD overlays/cluster-critical/kustomization.yaml
git commit -m "feat(envoy-gateway): add cluster-critical ArgoCD overlay"
```

---

### Task 3: Cloudflare ingress chart (GatewayClass + Gateway + EnvoyProxy + stable Service)

**Files:**

- Create: `charts/cloudflare-ingress/Chart.yaml`
- Create: `charts/cloudflare-ingress/values.yaml`
- Create: `charts/cloudflare-ingress/BUILD`
- Create: `charts/cloudflare-ingress/templates/_helpers.tpl`
- Create: `charts/cloudflare-ingress/templates/gatewayclass.yaml`
- Create: `charts/cloudflare-ingress/templates/envoyproxy.yaml`
- Create: `charts/cloudflare-ingress/templates/gateway.yaml`
- Create: `charts/cloudflare-ingress/templates/service.yaml`

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: cloudflare-ingress
description: Gateway API resources for Cloudflare tunnel ingress via Envoy Gateway
type: application
version: 1.0.0
appVersion: "1.0.0"

annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

```yaml
# Cloudflare ingress Gateway API configuration
# Environment-specific overrides live in overlays/<env>/cloudflare-ingress/values.yaml

gatewayClass:
  name: cloudflare-ingress
  controllerName: gateway.envoyproxy.io/gatewayclass-controller

envoyProxy:
  name: cloudflare-ingress-proxy
  # Namespace must match where Envoy Gateway control plane runs
  namespace: envoy-gateway-system
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 500m
      memory: 256Mi

gateway:
  name: cloudflare-ingress
  # Gateway lives in same namespace as the Envoy Gateway control plane
  namespace: envoy-gateway-system
  listener:
    port: 80

# Stable Service for the tunnel catch-all to target
service:
  name: cloudflare-ingress
  namespace: envoy-gateway-system
  port: 80
```

**Step 3: Create templates/\_helpers.tpl**

```
{{/*
Common labels
*/}}
{{- define "cloudflare-ingress.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
```

**Step 4: Create templates/envoyproxy.yaml**

The `EnvoyProxy` CRD controls the data-plane proxy resources per GatewayClass. It must be created before the GatewayClass that references it.

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: { { .Values.envoyProxy.name } }
  namespace: { { .Values.envoyProxy.namespace } }
  labels: { { - include "cloudflare-ingress.labels" . | nindent 4 } }
spec:
  provider:
    type: Kubernetes
    kubernetes:
      envoyDeployment:
        container:
          resources: { { - toYaml .Values.envoyProxy.resources | nindent 12 } }
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 65532
            runAsGroup: 65532
            capabilities:
              drop:
                - ALL
            seccompProfile:
              type: RuntimeDefault
```

**Step 5: Create templates/gatewayclass.yaml**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: { { .Values.gatewayClass.name } }
  labels: { { - include "cloudflare-ingress.labels" . | nindent 4 } }
spec:
  controllerName: { { .Values.gatewayClass.controllerName } }
  parametersRef:
    group: gateway.envoyproxy.io
    kind: EnvoyProxy
    name: { { .Values.envoyProxy.name } }
    namespace: { { .Values.envoyProxy.namespace } }
```

**Step 6: Create templates/gateway.yaml**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: { { .Values.gateway.name } }
  namespace: { { .Values.gateway.namespace } }
  labels: { { - include "cloudflare-ingress.labels" . | nindent 4 } }
spec:
  gatewayClassName: { { .Values.gatewayClass.name } }
  listeners:
    - name: http
      protocol: HTTP
      port: { { .Values.gateway.listener.port } }
      allowedRoutes:
        namespaces:
          from: All
```

**Step 7: Create templates/service.yaml**

Stable Service that selects the Envoy proxy pods by their well-known Gateway API labels. This gives the tunnel a predictable target name regardless of what Envoy Gateway names its auto-created Service.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: { { .Values.service.name } }
  namespace: { { .Values.service.namespace } }
  labels: { { - include "cloudflare-ingress.labels" . | nindent 4 } }
spec:
  type: ClusterIP
  ports:
    - port: { { .Values.service.port } }
      targetPort: { { .Values.gateway.listener.port } }
      protocol: TCP
      name: http
  selector:
    gateway.envoyproxy.io/owning-gateway-name: { { .Values.gateway.name } }
    gateway.envoyproxy.io/owning-gateway-namespace:
      { { .Values.gateway.namespace } }
```

**Step 8: Create BUILD**

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/prod/cloudflare-ingress:__pkg__"],
)
```

`lint = False` because the chart uses Gateway API CRDs and the `EnvoyProxy` CRD which aren't available during lint.

**Step 9: Verify template renders**

```bash
helm template cloudflare-ingress charts/cloudflare-ingress/ --namespace envoy-gateway-system
```

Expected: Renders EnvoyProxy, GatewayClass, Gateway, and Service. No errors.

**Step 10: Commit**

```bash
git add charts/cloudflare-ingress/
git commit -m "feat(cloudflare-ingress): add chart with GatewayClass, Gateway, EnvoyProxy, and stable Service"
```

---

### Task 4: Cloudflare ingress ArgoCD overlay (prod)

**Files:**

- Create: `overlays/prod/cloudflare-ingress/application.yaml`
- Create: `overlays/prod/cloudflare-ingress/kustomization.yaml`
- Create: `overlays/prod/cloudflare-ingress/values.yaml`
- Create: `overlays/prod/cloudflare-ingress/BUILD`
- Modify: `overlays/prod/kustomization.yaml`

**Step 1: Create application.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cloudflare-ingress
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: charts/cloudflare-ingress
    helm:
      valueFiles:
        - values.yaml
        - ../../overlays/prod/cloudflare-ingress/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: envoy-gateway-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

Note: No `CreateNamespace=true` -- the `envoy-gateway-system` namespace is created by the Envoy Gateway control plane in cluster-critical.

**Step 2: Create kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create values.yaml**

Prod overlay values. For this initial deployment the base values are sufficient, but we create the file for consistency and future overrides.

```yaml
# Production cloudflare-ingress overrides
# Base values in charts/cloudflare-ingress/values.yaml are suitable for initial deployment.
```

**Step 4: Create BUILD**

```starlark
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cloudflare-ingress",
    chart = "charts/cloudflare-ingress",
    chart_files = "//charts/cloudflare-ingress:chart",
    namespace = "envoy-gateway-system",
    release_name = "cloudflare-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-ingress:values.yaml",
        "values.yaml",
    ],
)
```

**Step 5: Add to prod kustomization**

Modify `overlays/prod/kustomization.yaml` -- add `./cloudflare-ingress` after `./api-gateway`:

```yaml
- ./api-gateway
- ./cloudflare-ingress
- ./cloudflare-tunnel
```

**Step 6: Commit**

```bash
git add overlays/prod/cloudflare-ingress/ overlays/prod/kustomization.yaml
git commit -m "feat(cloudflare-ingress): add prod ArgoCD overlay"
```

---

### Task 5: Wire tunnel catch-all to Envoy Gateway

**Files:**

- Modify: `overlays/prod/cloudflare-tunnel/values.yaml`

**Step 1: Change the catch-all**

In `overlays/prod/cloudflare-tunnel/values.yaml`, change the `catchAll` from `http_status:404` to the stable Envoy Gateway Service.

This is set via the chart's base `values.yaml` at `ingress.catchAll.service`. Override it in the overlay:

Add at the end of the `ingress:` block:

```yaml
ingress:
  routes:
    # ... all 12 routes unchanged ...
  # Route unmatched traffic through Envoy Gateway. With no HTTPRoutes deployed,
  # Envoy returns 404 -- same behaviour as the previous http_status:404 catch-all.
  # As routes are migrated to HTTPRoutes, remove them from the routes list above.
  catchAll:
    service: http://cloudflare-ingress.envoy-gateway-system.svc.cluster.local:80
```

**Step 2: Verify template renders**

```bash
helm template cluster-ingress charts/cloudflare-tunnel/ -f overlays/prod/cloudflare-tunnel/values.yaml --namespace ingress | grep -A2 'service:'
```

Expected: The last ingress entry should show `http://cloudflare-ingress.envoy-gateway-system.svc.cluster.local:80` as the catch-all.

**Step 3: Commit**

```bash
git add overlays/prod/cloudflare-tunnel/values.yaml
git commit -m "feat(cloudflare-tunnel): route catch-all traffic through Envoy Gateway"
```

---

### Task 6: Run format, verify CI locally, push and create PR

**Step 1: Run format**

```bash
format
```

This updates BUILD files via gazelle and formats all code. If it generates changes, commit them.

**Step 2: Verify helm templates render for both new overlays**

```bash
helm template envoy-gateway charts/envoy-gateway/ -f overlays/cluster-critical/envoy/values.yaml --namespace envoy-gateway-system > /dev/null
helm template cloudflare-ingress charts/cloudflare-ingress/ --namespace envoy-gateway-system > /dev/null
helm template cluster-ingress charts/cloudflare-tunnel/ -f overlays/prod/cloudflare-tunnel/values.yaml --namespace ingress > /dev/null
```

Expected: All three render without errors.

**Step 3: Push and create PR**

```bash
git push -u origin feat/envoy-gateway-ingress
gh pr create --title "feat: deploy Envoy Gateway with cloudflare-ingress Gateway" --body "..."
```

**Step 4: Monitor CI**

Poll `gh pr view <number> --json statusCheckRollup` until both "Format check" and "Test and push" pass. If format bot pushes a `style: auto-format` commit, rebase any follow-up fixes on top of it.

**Step 5: Verify deployment**

After merge, use ArgoCD MCP tools to verify:

- `envoy-gateway` app syncs in cluster-critical, pods healthy in `envoy-gateway-system`
- `prod-cloudflare-ingress` app syncs, GatewayClass/Gateway/EnvoyProxy/Service created
- `cloudflare-ingress` Service has endpoints (matching Envoy proxy pods)
- Existing routes still work (all 12 hostnames)
- A random hostname like `nonexistent.jomcgi.dev` returns 404 from Envoy (not Cloudflare's 404)
