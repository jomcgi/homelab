# RFC: Wiring App Images into Helm Chart Definitions via Bazel

**Status:** Draft (revised)
**Date:** 2026-03-10
**Author:** goose (AI agent)

---

## Problem

Image references are duplicated between `BUILD` files and `values.yaml` with no enforced link between them:

| Location | What's written manually |
|---|---|
| `tools/oci/{go,apko}_image.bzl` | `repository = "ghcr.io/jomcgi/homelab/myapp"` |
| `charts/<svc>/values.yaml` | `image.repository: ghcr.io/jomcgi/homelab/myapp` |

When someone adds a new service or renames a chart, these have to be kept in sync by hand. There's also no Bazel-level connection that makes chart template tests use the correct image reference.

---

## Solution: `images` dict on `helm_chart`

The fix is a first-class `images` attribute on `helm_chart`. Each entry maps a dot-notation Helm values path to a Bazel image label:

```starlark
helm_chart(
    name = "chart",
    publish = True,
    images = {
        "image":         "//charts/todo/image:image",
        "sidecar.image": "//services/trips/sidecar:image",
    },
)
```

Dict keys are dot-notation Helm values paths. Dict values are Bazel image labels. `helm_chart` resolves each label to a repository URL + stamp tag via the standard `OciImageInfo` provider, then generates a merged values fragment at build time. No separate targets, no repository string duplication, no boilerplate.

### Generated values fragment

Dot-notation keys expand to nested YAML. For a two-image chart:

```yaml
image:
  repository: ghcr.io/jomcgi/homelab/charts/todo
  tag: main-abc1234
sidecar:
  image:
    repository: ghcr.io/jomcgi/homelab/services/trips/sidecar
    tag: main-abc1234
```

Fragments are merged using `python3 -c` (always available in the Bazel sandbox).

### Why stamp tags — not digests

Images in this repo are already tagged with stamp variables: the `{name}.tags.txt` files produced by `go_image` / `apko_image` contain tags like `main-abc1234` (derived from `BUILD_SCM_BRANCH` + `BUILD_SCM_COMMIT`). This is the repo standard and it is intentionally unchanged.

Stamp tags are:

- **Human-readable.** `main-abc1234` immediately tells you the branch and commit. `sha256:3f2e1a4b…` is opaque.
- **Compatible with ArgoCD Image Updater.** Image Updater's tag subscriptions match on tag patterns (e.g. `^main-[a-f0-9]+$`). Digest references bypass the updater entirely, breaking automated rollouts.
- **Compatible with Kargo.** Kargo OCI repository subscriptions also operate on tags. Switching to digests would require significant Kargo reconfiguration.
- **Consistent with the rest of the repo.** Every image push in this monorepo uses stamp tags.

---

## Standardised image interface

For `helm_chart` to consume any image target generically, every image macro (`go_image`, `apko_image`) exposes two standard outputs and returns an `OciImageInfo` provider:

```starlark
OciImageInfo = provider(
    doc = "Standard interface for OCI image targets consumed by helm_chart.",
    fields = {
        "repository": "File: plain text OCI repository URL (e.g. ghcr.io/jomcgi/homelab/myapp)",
        "tags_file":  "File: stamp-resolved tag, one tag per line (e.g. main-abc1234)",
    },
)
```

| Output | Description |
|---|---|
| `{name}.tags.txt` | Stamp-resolved tag — already produced by most image macros |
| `{name}.repository` | Plain text file containing the OCI repository URL |

These outputs are added to the macros once. `helm_chart` reads `OciImageInfo.repository` and `OciImageInfo.tags_file` from every entry in `images` without needing to know whether the image is a Go binary, an apko base, or anything else.

---

## CI ordering as the safety guarantee

A chart in the registry will always have a corresponding image because the BuildBuddy workflow (fixed in PR #932) enforces sequential execution:

```
push_all (images)  →  helm:push_all (charts)
```

`helm:push_all` cannot start until all image pushes complete. If an image push fails, the chart is never pushed. There is no window where a chart references an image that doesn't exist.

This is a **workflow-level** ordering guarantee. No build graph enforcement is needed; the CI pipeline already provides it.

### OCI Helm chart versioning

OCI Helm charts get an auto-incrementing version tag on every push (this automation already exists). The chart version is the identity of the chart release — it is not tied to the image tag. Charts can be released independently of image builds (e.g. config-only changes), and the GitOps layer (ArgoCD Image Updater, Kargo) manages image tag updates separately.

---

## Integration with ArgoCD Image Updater and Kargo

Because `helm_chart` emits stamp tags rather than digests, the full GitOps pipeline continues to work without modification:

**ArgoCD Image Updater** watches the registry for new tags matching the configured pattern (e.g. `^main-[a-f0-9]+$`) and writes the latest tag back to the overlay `values.yaml`. This is the live rollout mechanism and is unchanged.

**Kargo** subscribes to OCI image repositories by tag pattern. Stamp tags match these subscriptions directly. Kargo promotion pipelines that advance an image tag through environments continue to work as designed.

Neither tool supports digest-only workflows without significant extra configuration. Stamp tags are the correct primitive here.

---

## Example `BUILD.bazel`

### Before

```starlark
# charts/todo/BUILD
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    publish = True,
    visibility = ["//overlays/prod/todo:__pkg__"],
)
```

```yaml
# charts/todo/values.yaml
image:
  repository: ghcr.io/jomcgi/homelab/charts/todo  # repeated from BUILD
  tag: main                                         # managed by ArgoCD Image Updater
```

### After

```starlark
# charts/todo/BUILD
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    publish = True,
    images = {
        "image": "//charts/todo/image:image",
    },
    visibility = ["//overlays/prod/todo:__pkg__"],
)
```

```yaml
# charts/todo/values.yaml
image:
  repository: ""  # set by Bazel via images dict
  tag: ""         # set by Bazel via images dict; ArgoCD Image Updater overrides in overlay
```

The `image.repository` duplication is eliminated. The `image.tag` in the overlay `values.yaml` is still managed by ArgoCD Image Updater at runtime — the Bazel-generated values are used for CI template testing and as the initial seed when a service is first deployed.

### Multi-image chart

A chart deploying multiple images is just a bigger dict — no extra targets:

```starlark
# charts/trips/BUILD
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    publish = True,
    images = {
        "image":         "//services/trips/api/image:image",
        "sidecar.image": "//services/trips/sidecar:image",
    },
    visibility = ["//overlays/prod/trips:__pkg__"],
)
```

This generates:

```yaml
image:
  repository: ghcr.io/jomcgi/homelab/services/trips/api
  tag: main-abc1234
sidecar:
  image:
    repository: ghcr.io/jomcgi/homelab/services/trips/sidecar
    tag: main-abc1234
```

---

## What was considered and rejected

### `helm_image_values` as a separate rule

A previous version of this RFC proposed a standalone `helm_image_values` target wired into `helm_chart` via an `image_values` attribute:

```starlark
helm_image_values(
    name = "image_values",
    image = "//charts/todo/image:image_stamped_ci.tags.txt",
    repository = "ghcr.io/jomcgi/homelab/charts/todo",
)

helm_chart(
    name = "chart",
    image_values = ":image_values",
    ...
)
```

**Rejected because the `images` dict is strictly better DX.** The separate target is unnecessary boilerplate: callers must declare an intermediate target per image and manually supply the `repository` string (duplicating what's already in the image macro). The `images` dict eliminates both: `helm_chart` reads `OciImageInfo.repository` directly from the image label, and no intermediate target is needed. `helm_image_values` works, but it adds ceremony with no benefit.

### Digest pinning

An earlier version of this RFC proposed using `{name}.digest` targets from `rules_oci` to pin `image.tag` to `sha256:…` digests in the generated values.

**Rejected for three reasons:**

1. **Breaks ArgoCD Image Updater.** Image Updater's tag subscriptions cannot match digest references. A chart deployed with `tag: sha256:abc…` would never receive automatic updates — the entire automated rollout pipeline would stop working.

2. **Breaks Kargo.** Kargo promotion pipelines operate on tags. Digest-only references are not supported by Kargo's OCI repository subscriptions without significant reconfiguration.

3. **Developer opacity.** `sha256:3f2e1a4b8c9d…` carries no human-readable signal. `main-abc1234` immediately communicates branch, recency, and traceability to a commit.

Stamp tags are the correct primitive. Digest references are appropriate for security-critical supply chain use cases (SBOM pinning, policy enforcement), but that is out of scope for this repo's current needs.

---

## Implementation plan

Four steps:

| Step | File | Effort |
|---|---|---|
| **1** | `tools/oci/go_image.bzl` + `apko_image.bzl` — add `{name}.repository` output and return `OciImageInfo` | Small |
| **2** | `rules_helm/chart.bzl` — add `images` dict attr; read `OciImageInfo` → generate merged values fragment | Small |
| **3** | Pilot on `charts/todo`, then roll out to other first-party charts | Mechanical |

Steps 1–2 land as a single PR. Pilot separately. The rule is simple enough to implement and test in under a day.
