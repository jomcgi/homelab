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

## Solution: `helm_image_values` rule

A new `helm_image_values` rule reads the image's stamp tag (already produced by `rules_oci`) and the repository string, then emits a Helm values YAML fragment:

```yaml
image:
  repository: ghcr.io/jomcgi/homelab/myapp
  tag: main-abc1234
```

This is the only change needed. No digest threading, no `.repository` genrules, no jq pipelines.

### Why stamp tags — not digests

Images in this repo are already tagged with stamp variables: the `{name}_stamped_ci.tags.txt` files produced by `go_image` / `apko_image` contain tags like `main-abc1234` (derived from `BUILD_SCM_BRANCH` + `BUILD_SCM_COMMIT`). This is the repo standard and it is intentionally unchanged.

Stamp tags are:

- **Human-readable.** `main-abc1234` immediately tells you the branch and commit. `sha256:3f2e1a4b…` is opaque — developers cannot reason about it at a glance.
- **Compatible with ArgoCD Image Updater.** Image Updater's tag subscriptions match on tag patterns (e.g. `^main-[a-f0-9]+$`). Digest references bypass the updater entirely, breaking the automated rollout pipeline.
- **Compatible with Kargo.** Kargo OCI repository subscriptions also operate on tags. Switching to digests would require significant Kargo reconfiguration.
- **Consistent with the rest of the repo.** Every other image push in this monorepo uses stamp tags. The `helm_image_values` rule follows the same pattern.

### What the rule looks like

```starlark
# rules_helm/image_values.bzl

def helm_image_values(name, image, repository, out = None):
    """Generate a Helm values fragment wiring a stamp-tagged image into chart values.

    Reads the stamp tag file already produced by go_image / apko_image and
    emits a values YAML with image.repository and image.tag populated.

    Args:
        name:       Rule name.
        image:      Label of the stamped tags file, e.g. "//charts/todo/image:image_stamped_ci.tags.txt"
        repository: OCI repository URL string, e.g. "ghcr.io/jomcgi/homelab/charts/todo"
        out:        Output filename (default: "{name}.yaml").
    """
    if out == None:
        out = name + ".yaml"

    native.genrule(
        name = name,
        srcs = [image],
        outs = [out],
        cmd = """
tag=$$(head -1 $(location {image}))
printf 'image:\\n  repository: {repo}\\n  tag: %s\\n' "$$tag" > $@
""".format(image = image, repo = repository),
    )
```

No external tools required — just `head` and `printf`, which are always available in the Bazel sandbox. The stamp tag file already exists as a build artifact; this rule simply surfaces its value into a YAML fragment that Helm can consume.

---

## CI ordering as the safety guarantee

A chart in the registry will always have a corresponding image because the BuildBuddy workflow (fixed in PR #932) enforces sequential execution:

```
push_all (images)  →  helm:push_all (charts)
```

`helm:push_all` cannot start until all image pushes complete. If an image push fails, the chart is never pushed. There is no window where a chart references an image that doesn't exist.

This is a **workflow-level** ordering guarantee. No build graph enforcement is needed; the CI pipeline already provides it.

### OCI Helm chart versioning

OCI Helm charts get an auto-incrementing version tag on every push (this automation already exists). The chart version is the identity of the chart release — it is not tied to the image tag. This is intentional: charts can be released independently of image builds (e.g. config-only changes), and the GitOps layer (ArgoCD Image Updater, Kargo) manages image tag updates separately.

---

## Integration with ArgoCD Image Updater and Kargo

Because `helm_image_values` emits a stamp tag rather than a digest, the full GitOps pipeline continues to work without modification:

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
load("//rules_helm:defs.bzl", "helm_chart", "helm_image_values")

helm_image_values(
    name = "image_values",
    image = "//charts/todo/image:image_stamped_ci.tags.txt",
    repository = "ghcr.io/jomcgi/homelab/charts/todo",
)

helm_chart(
    name = "chart",
    publish = True,
    image_values = ":image_values",
    visibility = ["//overlays/prod/todo:__pkg__"],
)
```

```yaml
# charts/todo/values.yaml
image:
  repository: ""  # set by Bazel via :image_values
  tag: ""         # set by Bazel via :image_values; ArgoCD Image Updater overrides in overlay
```

The `image.repository` duplication is eliminated. The `image.tag` in the overlay `values.yaml` is still managed by ArgoCD Image Updater at runtime — the Bazel-generated values are used for CI template testing and as the initial seed when a service is first deployed.

### Multi-image chart

For charts deploying multiple images (e.g. API + sidecar), add one `helm_image_values` target per image and pass them both to `helm_chart`:

```starlark
helm_image_values(
    name = "api_image_values",
    image = "//services/trips/api/image:image_stamped_ci.tags.txt",
    repository = "ghcr.io/jomcgi/homelab/services/trips/api",
)

helm_image_values(
    name = "imgproxy_image_values",
    image = "//services/trips/imgproxy/image:image_stamped_ci.tags.txt",
    repository = "ghcr.io/jomcgi/homelab/services/trips/imgproxy",
)
```

---

## What was considered and rejected

### Digest pinning

An earlier version of this RFC proposed using `{name}.digest` targets from `rules_oci` to pin `image.tag` to `sha256:…` digests in the generated values.

**Rejected for three reasons:**

1. **Breaks ArgoCD Image Updater.** Image Updater's tag subscriptions cannot match digest references. A chart deployed with `tag: sha256:abc…` would never receive automatic updates — the entire automated rollout pipeline would stop working.

2. **Breaks Kargo.** Kargo promotion pipelines operate on tags. Digest-only references are not supported by Kargo's OCI repository subscriptions without significant reconfiguration.

3. **Developer opacity.** `sha256:3f2e1a4b8c9d…` carries no human-readable signal. `main-abc1234` immediately communicates branch, recency, and traceability to a commit. Readable values are better for GitOps workflows where developers inspect and reason about what's deployed.

Stamp tags are the correct primitive. Digest references are appropriate for security-critical supply chain use cases (SBOM pinning, policy enforcement), but that is out of scope for this repo's current needs.

### `{name}.repository` genrule

Also proposed in the earlier RFC: emit the repository URL as a Bazel file artifact from each image macro so downstream rules could depend on it at build time.

**Rejected because it's unnecessary.** The `helm_image_values` rule takes `repository` as a string attribute. The repository URL is stable — it only changes if the image is renamed, at which point both the `apko_image` / `go_image` call and the `helm_image_values` call need updating anyway. There is no runtime derivation needed; a string argument is sufficient and simpler.

---

## Implementation plan

Three small steps:

| Step | File | Effort |
|---|---|---|
| **1** | `rules_helm/image_values.bzl` — new `helm_image_values` rule | Small |
| **2** | `rules_helm/chart.bzl` — add optional `image_values` attr to `helm_chart` | Small |
| **3** | Pilot on `charts/todo`, then roll out to other first-party charts | Mechanical |

Start with steps 1–2 as a single PR. Pilot separately. The rule is simple enough to implement and test in under a day.
