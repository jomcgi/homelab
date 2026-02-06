# Evaluation: cdk8s Migration for Homelab

## Executive Summary

**Verdict: Worthwhile long-term investment if you commit to building `rules_cdk8s`.**

ArgoCD supports cdk8s via Config Management Plugins (CMP), enabling cdk8s definitions as source of truth. Combined with Bazel caching and Gazelle auto-generation, this creates a "fix once, fix everywhere" workflow.

**Key value**: Not just about 23 charts today, but:
- Type-safe infrastructure catching errors at compile time
- Reusable constructs compounding in value
- Bazel caching for incremental builds
- Scalable pattern for future services

## Current Pain Points

| Issue | Evidence |
|-------|----------|
| Helper duplication | 8 charts with identical `_helpers.tpl` |
| Deployment boilerplate | Security contexts/probes repeated 34+ times |
| Multi-component repetition | marine/trips/claude repeat config per component |
| No shared templates | Helm lacks chart inheritance |
| Values repetition | Each overlay defines everything independently |

**What cdk8s solves:**
- True code reuse via functions
- Type safety with compile-time validation
- IDE support (autocomplete, refactoring)
- No YAML indentation bugs

## ArgoCD + cdk8s Architecture

```
┌─────────────────────────────────────────────────────────┐
│ ArgoCD Repo Server Pod                                   │
│  ┌────────────────┐    ┌─────────────────────────────┐  │
│  │ repo-server    │◄──►│ cdk8s-cmp sidecar           │  │
│  │ (main)         │    │ - runs cdk8s synth          │  │
│  │                │    │ - outputs YAML to stdout    │  │
│  └────────────────┘    └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         ▲
         │
         │ Git push (cdk8s code)
         │
    ┌────┴────┐
    │   Git   │
    └─────────┘

Flow: Git push → ArgoCD detects → CMP runs synth → Apply manifests
```

**Available CMP images** (from [akuity/cdk8s-cmp](https://github.com/akuity/cdk8s-cmp)):
- `ghcr.io/akuity/cdk8s-cmp-typescript`
- `ghcr.io/akuity/cdk8s-cmp-python`
- `ghcr.io/akuity/cdk8s-cmp-go`

### Adding CMP to ArgoCD

```yaml
# clusters/homelab/argocd/values.yaml
argo-cd:
  repoServer:
    extraContainers:
      - name: cdk8s-typescript
        image: ghcr.io/akuity/cdk8s-cmp-typescript:latest
        command: [/var/run/argocd/argocd-cmp-server]
        securityContext:
          runAsNonRoot: true
          runAsUser: 999
        volumeMounts:
          - name: var-files
            mountPath: /var/run/argocd
          - name: plugins
            mountPath: /home/argocd/cmp-server/plugins
```

## Trade-offs

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Resource name changes trigger recreate | Use explicit `name` in construct props |
| CMP maturity (18 stars, 8 commits) | Fork/maintain own or use custom images |
| rules_cdk8s doesn't exist | Start simple (genrule), evolve incrementally |
| Learning curve | TypeScript familiar, cdk8s mirrors K8s API |

### Compounding Benefits

| Benefit | Year 1 | Year 3+ |
|---------|--------|---------|
| Type safety | Catches misconfigurations | Prevents entire bug classes |
| Constructs | `SecureDeployment`, `ServiceWithProbes` | Battle-tested pattern library |
| Bazel caching | Faster on unchanged charts | Near-instant for small changes |
| Gazelle | Less BUILD maintenance | Zero-friction new services |

## Implementation: Custom Bazel-Built CMP

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Build Time (Bazel)                                       │
│                                                          │
│  pyproject.toml → requirements/runtime.txt → CMP Image  │
│  (cdk8s deps)     (locked versions)         (baked in)  │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│ Runtime (ArgoCD)                                         │
│                                                          │
│  repo-server ◄──► cdk8s-cmp ──► cdk8s synth --stdout   │
│                   (custom img)   (fast, ready)          │
└─────────────────────────────────────────────────────────┘
```

### Phase 1: Custom CMP Image

**1. Add dependencies** (`pyproject.toml`):
```toml
dependencies = [
    "cdk8s~=2.68",
    "cdk8s-cli~=2.68",
    "constructs~=10.0",
]
```

**2. CMP plugin config** (`tools/cdk8s-cmp/plugin.yaml`):
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ConfigManagementPlugin
metadata:
  name: cdk8s-bazel
spec:
  version: v1.0
  discover:
    fileName: "cdk8s.yaml"
  generate:
    command: [cdk8s, synth, --stdout]
```

**3. BUILD file** (`tools/cdk8s-cmp/BUILD`):
```python
load("//tools/oci:py3_image.bzl", "py3_image")

py3_image(
    name = "image",
    binary = ":cdk8s_cmp",
    repository = "ghcr.io/jomcgi/homelab/cdk8s-cmp",
)
```

### Phase 2: First cdk8s Service

**Directory structure**:
```
cdk8s/
├── lib/                      # Shared constructs (py_library)
│   ├── BUILD
│   └── secure_deployment.py
└── stargazer/                # First service
    ├── BUILD
    ├── cdk8s.yaml
    └── main.py
```

**Shared construct** (`cdk8s/lib/secure_deployment.py`):
```python
from constructs import Construct
from imports.k8s import KubeDeployment

class SecureDeployment(Construct):
    """Deployment with security best practices."""

    def __init__(self, scope, id, *, name, image, port, replicas=1,
                 health_path="/health"):
        super().__init__(scope, id)

        KubeDeployment(self, "deployment",
            metadata={"name": name},
            spec={
                "replicas": replicas,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "securityContext": {
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [{
                            "name": name,
                            "image": image,
                            "ports": [{"containerPort": port}],
                            "securityContext": {
                                "readOnlyRootFilesystem": True,
                                "allowPrivilegeEscalation": False,
                                "runAsNonRoot": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "livenessProbe": {
                                "httpGet": {"path": health_path, "port": port},
                            },
                        }],
                    },
                },
            },
        )
```

**Service chart** (`cdk8s/stargazer/main.py`):
```python
from cdk8s import App, Chart
from lib.secure_deployment import SecureDeployment

class StargazerChart(Chart):
    def __init__(self, scope, id):
        super().__init__(scope, id)
        SecureDeployment(self, "api",
            name="stargazer",
            image="ghcr.io/jomcgi/homelab/stargazer:main",
            port=8000,
            replicas=2,
        )

app = App()
StargazerChart(app, "stargazer")
app.synth()
```

### Phase 3: Bazel Integration

**Custom rule** (`tools/cdk8s/defs.bzl`):
```python
def py_cdk8s_chart(name, srcs, deps = []):
    """Macro for cdk8s charts with synth + validation."""

    native.py_library(
        name = name + "_lib",
        srcs = srcs,
        deps = deps + ["@pip//cdk8s", "@pip//constructs"],
    )

    cdk8s_synth(
        name = name,
        srcs = srcs,
        deps = [name + "_lib"] + deps,
    )
```

**Usage**:
```python
# cdk8s/stargazer/BUILD
load("//tools/cdk8s:defs.bzl", "py_cdk8s_chart")

py_cdk8s_chart(
    name = "stargazer",
    srcs = ["main.py"],
    deps = ["//cdk8s/lib"],
)
```

**Benefits**:
- `bazel build //cdk8s/stargazer` - local synth for review
- `bazel test //cdk8s/...` - validate all charts compile
- Gazelle can auto-generate targets (Phase 4)

## cdk8s Construct Hierarchy

```
┌─────────────────────────────────────────────────┐
│ App (cdk8s.App)                                  │
│  ├─ StargazerChart (cdk8s.Chart)                │
│  │   └─ SecureDeployment (Construct)            │
│  │       ├─ KubeDeployment (K8s API)            │
│  │       └─ KubeService (K8s API)               │
│  ├─ MarineChart (cdk8s.Chart)                   │
│  │   ├─ SecureDeployment (backend)              │
│  │   ├─ SecureDeployment (worker)               │
│  │   └─ PostgresCluster (Construct)             │
└─────────────────────────────────────────────────┘

Reusable Constructs Library:
  - SecureDeployment
  - ClusterIPService
  - CloudflareIngress
  - PostgresCluster
  - ObservableService (auto OTEL annotations)
```

## K8s Imports Management

**Strategy**: Pre-generate and version control K8s types (~2.5MB) once:

```bash
# tools/cdk8s/regenerate-imports.sh
cd cdk8s/imports
cdk8s import k8s --output .
```

**Bazel integration**:
```python
# cdk8s/imports/BUILD
py_library(
    name = "k8s",
    srcs = glob(["k8s/**/*.py"]),
    visibility = ["//cdk8s:__subpackages__"],
)
```

**Rationale**: Generated code rarely changes (only on K8s API bumps), version control provides audit trail.

## Helm Chart Distribution

### Problem: cdk8s `--format helm` Limitations

- Templates are static YAML (no `{{ .Values }}`)
- Users cannot customize via values.yaml
- Cannot deploy multiple releases (name collisions)

### Solution: Custom Post-Processor

**1. Value placeholders** (`cdk8s/lib/values.py`):
```python
class HelmValue:
    """Marker for Helm template variables."""
    def __init__(self, path: str, default):
        self.path = path
        self.default = default

    def __str__(self):
        return f"__HELM_VALUE__{self.path}__"

# Usage:
annotations = {
    "cloudflare.ingress.hostname": HelmValue("hostname", "example.com"),
}
```

**2. Post-processor**:
```python
# tools/cdk8s/helm_export.py
def convert_to_helm_chart(yaml_content: str) -> tuple[str, dict]:
    template = re.sub(
        r'__HELM_VALUE__([^_]+)__',
        r'{{ .Values.\1 }}',
        yaml_content
    )
    return template, values
```

**3. Bazel rule**:
```python
def py_cdk8s_helm_chart(name, srcs, deps = []):
    py_cdk8s_synth(name = name + "_raw", ...)

    native.genrule(
        name = name,
        srcs = [name + "_raw"],
        outs = ["helm/Chart.yaml", "helm/values.yaml",
                "helm/templates/manifests.yaml"],
        cmd = "$(location //tools/cdk8s:helm_export) ...",
    )
```

## Migration Strategy

1. **Week 1**: Build/deploy custom CMP image
2. **Week 2**: Create `cdk8s/lib/` with shared constructs
3. **Week 3**: Migrate stargazer (simple service)
4. **Week 4+**: Incremental migration, keep Helm as fallback

## Validation

```bash
# Build CMP
bazel build //tools/cdk8s-cmp:image

# Local synth
bazel build //cdk8s/stargazer
cat bazel-bin/cdk8s/stargazer/stargazer.yaml

# Deploy to ArgoCD
kubectl logs -n argocd <repo-server-pod> -c cdk8s-cmp
```

## Critical Files

| File | Action |
|------|--------|
| `pyproject.toml` | Add cdk8s deps |
| `tools/cdk8s-cmp/` | New CMP image |
| `tools/cdk8s/defs.bzl` | Bazel rules |
| `clusters/homelab/argocd/values.yaml` | Add CMP sidecar |
| `cdk8s/lib/` | Shared constructs |
| `cdk8s/stargazer/` | First service |

## References

- [cdk8s GitHub](https://github.com/cdk8s-team/cdk8s)
- [ArgoCD Config Management Plugins](https://argo-cd.readthedocs.io/en/stable/operator-manual/config-management-plugins/)
- [akuity/cdk8s-cmp](https://github.com/akuity/cdk8s-cmp)
