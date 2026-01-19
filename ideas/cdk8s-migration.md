# Evaluation: cdk8s Migration for Homelab

## Executive Summary

**Revised answer: This could be a worthwhile long-term investment if you're willing to commit to building `rules_cdk8s`.**

ArgoCD supports cdk8s via [Config Management Plugins](https://argo-cd.readthedocs.io/en/stable/operator-manual/config-management-plugins/) (CMP), which means cdk8s definitions can be your source of truth. Combined with Bazel's caching and Gazelle's auto-generation, you could create a powerful "fix once, fix everywhere" workflow.

**Key insight**: The investment isn't just about your 23 charts today - it's about:
1. Type-safe infrastructure that catches errors at compile time
2. Reusable constructs that compound in value as you add services
3. Bazel caching making `cdk8s synth` incremental and fast
4. A pattern you can use for years

---

## Current State Analysis

### Your Pain Points (Validated by Codebase Exploration)

| Issue | Evidence |
|-------|----------|
| Helper duplication | 8 charts with nearly-identical `_helpers.tpl` (name, fullname, labels, selectorLabels) |
| Deployment boilerplate | Security contexts, probes, resource blocks repeated 34+ times |
| Multi-component repetition | marine/trips/claude charts repeat image/replicas/resources per component |
| No shared templates | Helm doesn't support chart inheritance, only dependencies |
| Values repetition | Each overlay defines everything independently, no layering |

### What cdk8s Would Solve

1. **True code reuse**: Write a `SecureDeployment()` function once, use everywhere
2. **Type safety**: Compile-time validation instead of runtime YAML errors
3. **IDE support**: Autocomplete, refactoring, jump-to-definition
4. **Eliminates indentation bugs**: No more YAML spacing issues

---

## ArgoCD + cdk8s: How It Works

### Config Management Plugin Architecture

ArgoCD supports cdk8s through [Config Management Plugins](https://argo-cd.readthedocs.io/en/stable/operator-manual/config-management-plugins/) (CMPs). The setup involves:

```
┌─────────────────────────────────────────────────────────┐
│ argocd-repo-server pod                                   │
│  ┌────────────────┐    ┌─────────────────────────────┐  │
│  │ repo-server    │◄──►│ cdk8s-cmp sidecar           │  │
│  │ (main)         │    │ - runs cdk8s synth          │  │
│  │                │    │ - outputs YAML to stdout    │  │
│  └────────────────┘    └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Available images** from [akuity/cdk8s-cmp](https://github.com/akuity/cdk8s-cmp):
- `ghcr.io/akuity/cdk8s-cmp-typescript`
- `ghcr.io/akuity/cdk8s-cmp-python`
- `ghcr.io/akuity/cdk8s-cmp-go`

### Your GitOps Flow With cdk8s

```
Git push (cdk8s code) → ArgoCD detects → CMP runs `cdk8s synth` → Apply manifests
```

**This means cdk8s IS your source of truth** - no pre-commit rendering needed. ArgoCD renders on-demand.

### Adding CMP to Your ArgoCD

Your current ArgoCD config (`clusters/homelab/argocd/values.yaml`) is minimal. Adding a CMP sidecar:

```yaml
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
          - name: cdk8s-cmp-config
            mountPath: /home/argocd/cmp-server/config/plugin.yaml
            subPath: plugin.yaml
    volumes:
      - name: cdk8s-cmp-config
        configMap:
          name: cdk8s-cmp-config
```

---

## Trade-offs to Consider

### Risks

| Risk | Mitigation |
|------|------------|
| **Resource naming hashes** - Refactoring construct names can trigger delete/recreate | Use explicit `name` in construct props, establish naming conventions |
| **CMP maturity** - akuity/cdk8s-cmp has 18 stars, 8 commits | Fork and maintain your own if needed, or use custom images |
| **rules_cdk8s doesn't exist** - You'd build it from scratch | Start simple (genrule wrapper), evolve as needed |
| **Learning curve** - Team needs to learn cdk8s patterns | TypeScript is familiar, cdk8s API mirrors K8s API |

### Benefits That Compound

| Benefit | Year 1 | Year 3+ |
|---------|--------|---------|
| **Type safety** | Catches misconfigurations | Prevents entire classes of bugs |
| **Reusable constructs** | `SecureDeployment`, `ServiceWithProbes` | Library of battle-tested patterns |
| **Bazel caching** | Faster synth on unchanged charts | Near-instant builds for small changes |
| **Gazelle auto-gen** | Less BUILD file maintenance | Zero-friction new services |

---

## Implementation Plan: Bazel-Built CMP Image

**Key insight**: Build a custom CMP sidecar with Bazel-managed dependencies. No `pipenv update` at render time - deps are pre-installed.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Build Time (Bazel)                                               │
│                                                                  │
│  pyproject.toml ──► requirements/runtime.txt ──► CMP Image      │
│  (cdk8s dep)        (locked versions)           (deps baked in) │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Runtime (ArgoCD)                                                 │
│                                                                  │
│  repo-server ◄──► cdk8s-cmp sidecar ──► cdk8s synth --stdout   │
│                   (your custom image)    (fast, deps ready)     │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 1: Custom CMP Image

**Goal**: Build CMP sidecar using your existing `py3_image` patterns

**1. Add cdk8s to dependencies** (`pyproject.toml`):
```toml
dependencies = [
    # ... existing deps
    "cdk8s~=2.68",
    "cdk8s-cli~=2.68",  # For synth command
    "constructs~=10.0",
]
```

**2. Create CMP entrypoint** (`tools/cdk8s-cmp/main.py`):
```python
#!/usr/bin/env python3
"""cdk8s Config Management Plugin for ArgoCD."""
import subprocess
import sys

def main():
    # argocd-cmp-server calls this with specific args
    # We just delegate to cdk8s synth
    result = subprocess.run(
        ["cdk8s", "synth", "--stdout"],
        capture_output=False,
    )
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
```

**3. Plugin config** (`tools/cdk8s-cmp/plugin.yaml`):
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ConfigManagementPlugin
metadata:
  name: cdk8s-bazel
spec:
  version: v1.0
  discover:
    fileName: "cdk8s.yaml"  # Only trigger on cdk8s projects
  generate:
    command: [python, -m, cdk8s_cmp]  # Or direct cdk8s synth
```

**4. BUILD file** (`tools/cdk8s-cmp/BUILD`):
```python
load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_binary(
    name = "cdk8s_cmp",
    srcs = ["main.py"],
    deps = [
        "@pip//cdk8s",
        "@pip//cdk8s_cli",
        "@pip//constructs",
    ],
)

py3_image(
    name = "image",
    binary = ":cdk8s_cmp",
    repository = "ghcr.io/jomcgi/homelab/cdk8s-cmp",
    # Include argocd-cmp-server binary
    # This needs special handling - see Phase 1b
)
```

**5. ArgoCD sidecar config** (`clusters/homelab/argocd/values.yaml`):
```yaml
argo-cd:
  repoServer:
    extraContainers:
      - name: cdk8s-cmp
        image: ghcr.io/jomcgi/homelab/cdk8s-cmp:main
        command: [/var/run/argocd/argocd-cmp-server]
        securityContext:
          runAsNonRoot: true
          runAsUser: 999
        volumeMounts:
          - name: var-files
            mountPath: /var/run/argocd
          - name: plugins
            mountPath: /home/argocd/cmp-server/plugins
          - name: cmp-tmp
            mountPath: /tmp
```

### Phase 1b: CMP Image Details

The CMP image needs two things the akuity images provide:
1. **argocd-cmp-server binary** - gRPC server that ArgoCD calls
2. **cdk8s + Python deps** - for running synth

**Option A**: Multi-stage build
```dockerfile
FROM quay.io/argoproj/argocd:latest AS argocd
FROM your-py3-image AS final
COPY --from=argocd /usr/local/bin/argocd-cmp-server /usr/local/bin/
```

**Option B**: Bazel `oci_image` with layers
```python
oci_image(
    name = "cdk8s_cmp_image",
    base = "@python_base",
    tars = [
        ":py_layers",           # Python deps
        ":argocd_cmp_server",   # Binary from argocd image
    ],
)
```

### Phase 2: First cdk8s Service (Python)

**Goal**: Migrate one service to validate the workflow

**Directory structure**:
```
cdk8s/
├── lib/                          # Shared constructs (py_library)
│   ├── BUILD
│   ├── __init__.py
│   ├── secure_deployment.py
│   └── service.py
├── stargazer/                    # First service
│   ├── BUILD
│   ├── cdk8s.yaml               # Required for CMP discovery
│   ├── main.py                  # App + Chart definition
│   └── __init__.py
└── BUILD                         # Package root
```

**cdk8s/lib/secure_deployment.py**:
```python
from constructs import Construct
from cdk8s import Chart
from imports.k8s import (
    KubeDeployment, KubeService,
    ContainerSecurityContext, PodSecurityContext,
    Probe, HttpGetAction, ResourceRequirements,
)

class SecureDeployment(Construct):
    """Deployment with security best practices baked in."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        name: str,
        image: str,
        port: int,
        replicas: int = 1,
        health_path: str = "/health",
        ready_path: str = "/ready",
    ):
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
                            "readinessProbe": {
                                "httpGet": {"path": ready_path, "port": port},
                            },
                        }],
                    },
                },
            },
        )
```

**cdk8s/stargazer/main.py**:
```python
from cdk8s import App, Chart
from constructs import Construct
from lib.secure_deployment import SecureDeployment

class StargazerChart(Chart):
    def __init__(self, scope: Construct, id: str):
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

**cdk8s/stargazer/cdk8s.yaml**:
```yaml
language: python
app: python main.py
```

### Phase 3: Bazel Integration (py_cdk8s_synth)

**Goal**: Local development + CI validation with Bazel

**tools/cdk8s/defs.bzl**:
```python
"""Bazel rules for cdk8s synthesis."""

def _cdk8s_synth_impl(ctx):
    """Run cdk8s synth and capture output."""
    output = ctx.actions.declare_file(ctx.attr.name + ".yaml")

    ctx.actions.run(
        outputs = [output],
        inputs = ctx.files.srcs + ctx.files.deps,
        executable = ctx.executable._cdk8s,
        arguments = ["synth", "--stdout"],
        env = {"PYTHONPATH": ":".join([f.dirname for f in ctx.files.deps])},
        mnemonic = "Cdk8sSynth",
    )

    return [DefaultInfo(files = depset([output]))]

cdk8s_synth = rule(
    implementation = _cdk8s_synth_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = [".py"]),
        "deps": attr.label_list(providers = [PyInfo]),
        "_cdk8s": attr.label(
            default = "@pip//cdk8s_cli",
            executable = True,
            cfg = "exec",
        ),
    },
)

def py_cdk8s_chart(name, srcs, deps = [], **kwargs):
    """Macro for cdk8s Python charts with synth + validation."""

    native.py_library(
        name = name + "_lib",
        srcs = srcs,
        deps = deps + ["@pip//cdk8s", "@pip//constructs"],
    )

    cdk8s_synth(
        name = name,
        srcs = srcs,
        deps = [name + "_lib"] + deps,
        **kwargs
    )
```

**Usage in BUILD**:
```python
load("//tools/cdk8s:defs.bzl", "py_cdk8s_chart")

py_cdk8s_chart(
    name = "stargazer",
    srcs = ["main.py"],
    deps = ["//cdk8s/lib"],
)
```

**Benefits**:
- `bazel build //cdk8s/stargazer` - synthesizes locally for review
- `bazel test //cdk8s/...` - validates all charts compile
- Gazelle can auto-generate `py_cdk8s_chart` targets (Phase 4)

### Phase 4: Gazelle Extension (Optional)

**Goal**: Auto-detect cdk8s projects and generate BUILD files

Extend Python Gazelle to recognize `cdk8s.yaml`:

```go
// gazelle/cdk8s/cdk8s.go
func (l *cdk8sLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
    // If cdk8s.yaml exists in directory, generate py_cdk8s_chart
    if hasCdk8sYaml(args.Dir) {
        return generateCdk8sChart(args)
    }
    return language.GenerateResult{}
}
```

This is optional - explicit `py_cdk8s_chart` macros work fine.

### Phase 5: Migration Strategy

1. **Week 1**: Build and deploy custom CMP image
2. **Week 2**: Create `cdk8s/lib/` with shared constructs
3. **Week 3**: Migrate `stargazer` (simple dev service)
4. **Week 4+**: Migrate services incrementally, keep Helm as fallback

---

## Verification Plan

### Phase 1 Validation
```bash
# 1. Build CMP image
bazel build //tools/cdk8s-cmp:image

# 2. Load and test locally
bazel run //tools/cdk8s-cmp:image.load
docker run --rm ghcr.io/jomcgi/homelab/cdk8s-cmp:latest cdk8s --version

# 3. Deploy to ArgoCD
# Push image, update values.yaml, wait for ArgoCD sync
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-repo-server

# 4. Verify sidecar
kubectl logs -n argocd <repo-server-pod> -c cdk8s-cmp
```

### Phase 2 Validation
```bash
# 1. Local synth
bazel build //cdk8s/stargazer
cat bazel-bin/cdk8s/stargazer/stargazer.yaml

# 2. Create ArgoCD Application pointing to cdk8s/stargazer/
# 3. Verify ArgoCD syncs via CMP
argocd app get stargazer --show-operation
```

---

## Critical Files to Create/Modify

| File | Action |
|------|--------|
| `pyproject.toml` | Add cdk8s, constructs deps |
| `tools/cdk8s-cmp/` | New directory for CMP image |
| `tools/cdk8s/defs.bzl` | New Bazel rules |
| `clusters/homelab/argocd/values.yaml` | Add CMP sidecar |
| `cdk8s/lib/` | Shared constructs library |
| `cdk8s/stargazer/` | First migrated service |

---

## Sources

- [cdk8s GitHub](https://github.com/cdk8s-team/cdk8s)
- [Abandon the Helm, leveraging CDK for Kubernetes (2025)](https://www.technowizardry.net/2025/04/abandon-the-helm-leveraging-cdk-for-kubernetes/)
- [7 Helm alternatives (Northflank)](https://northflank.com/blog/7-helm-alternatives-to-simplify-kubernetes-deployments)
- [cdk8s Overview (Palark)](https://blog.palark.com/cdk8s-framework-for-kubernetes-manifests/)
- [rules_k8s (Bazel)](https://github.com/bazelbuild/rules_k8s)
- [Gazelle](https://github.com/bazel-contrib/bazel-gazelle)
- [ArgoCD Config Management Plugins](https://argo-cd.readthedocs.io/en/stable/operator-manual/config-management-plugins/)
- [akuity/cdk8s-cmp](https://github.com/akuity/cdk8s-cmp)
