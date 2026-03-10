# RFC: Wiring App Images into Helm Chart Definitions via Bazel

**Status:** Draft
**Date:** 2026-03-10
**Author:** goose (AI agent)

---

## Background

The homelab monorepo uses two complementary build systems:

- **`rules_oci`** (via the `go_image` and `apko_image` macros in `tools/oci/`) to build and push multi-platform OCI container images.
- **`rules_helm`** (the local `rules_helm/` package) to package and push OCI Helm charts.

Today, there is **no Bazel-level connection** between these two systems. Image references are duplicated across:

| Location | How it's used |
|---|---|
| `tools/oci/{go,apko}_image.bzl` | `repository = "ghcr.io/…"` attr on `oci_push` |
| `charts/<svc>/values.yaml` | `image.repository: ghcr.io/…` + `image.tag: main` (default) |
| `overlays/<env>/<svc>/values.yaml` | `image.tag: main@sha256:…` (written by ArgoCD Image Updater) |

ArgoCD Image Updater bridges the runtime gap by writing digest-pinned tags back to git on every push. But Bazel has no knowledge of which image a given chart deploys, making it impossible to:

- Verify that the chart and its image are in sync at build time.
- Run `helm template` tests with the exact image the chart will deploy.
- Have a single Bazel build graph that spans source → image → chart → deployment manifest.

---

## Goals

1. **Single source of truth.** The `oci_push` / `oci_image` target in a chart's `BUILD` file is the canonical reference for what image the chart deploys — not a string repeated in YAML.
2. **Hermetic and reproducible.** Given the same source inputs, Bazel always produces the same image digest and the same Helm values fragment referencing it.
3. **Minimal new surface area.** Leverage what already exists (`rules_oci`'s `.digest` targets, `aspect_bazel_lib`'s `jq` and `expand_template`, the existing `helm_chart` macro) rather than inventing a parallel build system.
4. **Compatible with ArgoCD GitOps.** The proposal should complement ArgoCD Image Updater (which handles live rollouts) rather than replace it.

---

## Codebase Survey

### Image targets today

**`go_image` macro** (`tools/oci/go_image.bzl`):
- Creates `oci_image` (or `oci_image_index` for multi-platform).
- Creates `{name}.push` — an `oci_push` with a `repository` string.
- Creates `{name}_stamped_ci.tags.txt` / `{name}_stamped_local.tags.txt` — stamp-backed tag files.

**`apko_image` macro** (`tools/oci/apko_image.bzl`):
- Same structure as `go_image`, but uses `apko` for the OS layer.
- The `repository` attribute is the registry path, e.g. `"ghcr.io/jomcgi/homelab/charts/todo"`.

Neither macro exposes the **image repository** or **digest** as a Bazel build-time artifact (file) that other rules can depend on.

### Digest support in `rules_oci`

`rules_oci` (v2.2.6, used here) already provides a `{name}.digest` target for every `oci_image` and `oci_image_index`. This target:
- Is a **build-time** output — no registry push required.
- Produces a plain text file containing `sha256:<hex>`.
- Is generated via a `jq` filter over the image's local `index.json`:
  ```starlark
  jq(filter = ".manifests[0].digest", srcs = ["{name}_index.json"])
  ```
- Is deterministic: the same source inputs produce the same digest (content-addressed OCI images).

This is the key primitive for hermetic image wiring.

### Helm chart targets today

The `helm_chart` macro (`rules_helm/chart.bzl`) creates:
- A filegroup of all chart sources.
- A `helm_lint_test`.
- Optionally, `{name}.package` (`helm_package`) and `{name}.push` (`helm_push`) when `publish = True`.

`helm_package` takes `srcs = glob(["**/*"])` and calls `helm package` to produce a `.tgz`. It knows nothing about images.

### ArgoCD Image Updater

Image Updater watches a registry tag (e.g. `ghcr.io/jomcgi/homelab/charts/todo:main`) and writes the digest-pinned tag (e.g. `main@sha256:abc...`) back to `overlays/<env>/<svc>/values.yaml`. This works well at runtime, but requires the initial `image.repository` to already be correct in the values file, and doesn't give Bazel visibility into the image reference.

---

## Design Proposal

The recommended approach has three components:

### Component 1: `{name}.repository` file in image macros

Extend `go_image` and `apko_image` to emit a `{name}.repository` text file containing the repository URL:

```starlark
# tools/oci/go_image.bzl (and apko_image.bzl)
native.genrule(
    name = name + "_repository",
    outs = [name + ".repository"],
    cmd = "echo -n '{}' > $@".format(
        repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name()
    ),
)
```

This small addition makes the repository URL a **first-class Bazel artifact** that other rules can `dep` on, without any runtime side effects.

> **Why a file and not a provider?** Starlark providers only cross the rule boundary at analysis time. Because `helm_image_values` (below) needs to combine repository + digest into a YAML file at **build time** (not analysis time), a file-based approach integrating with `genrule` or `jq` is simpler and works with cached remote execution on BuildBuddy.

### Component 2: `helm_image_values` rule

A new rule in `rules_helm/image_values.bzl` that reads repository + digest files and generates a `values.yaml` fragment:

```starlark
# rules_helm/image_values.bzl

def helm_image_values(name, images, out = None):
    """Generate a Helm values YAML fragment wiring oci_image targets to chart values.

    For each entry in `images`, reads the image's .repository and .digest files
    and generates a YAML fragment suitable for use as a --values override.

    Args:
        name:   Rule name.
        images: Dict mapping Helm values path → oci_image or oci_image_index label.
                The key is the dot-separated Helm path prefix for image.repository / image.tag.
                Example: {"image": "//charts/todo/image:image"}
                Example: {"api.image": "//services/api/image:image",
                           "sidecar.image": "//services/sidecar/image:image"}
        out:    Output filename (default: "{name}.yaml").
    """
    if out == None:
        out = name + ".yaml"

    srcs = []
    # Build a jq expression that assembles the YAML from each image's files
    jq_parts = []

    for values_path, image_target in images.items():
        repo_file = image_target + ".repository"
        digest_file = image_target + ".digest"
        srcs += [repo_file, digest_file]

        # Each image contributes a key-value pair to a jq object
        jq_parts.append(
            '"{path}": {{"repository": $inputs[{i}], "tag": $inputs[{j}]}}'.format(
                path = values_path,
                i = len(jq_parts) * 2,
                j = len(jq_parts) * 2 + 1,
            )
        )

    # Build jq filter to produce the final object
    jq_filter = "{ " + ", ".join(jq_parts) + " } | to_entries | map(.key |= split(\".\")) | ..."
    # (see full implementation note below)

    native.genrule(
        name = name,
        srcs = srcs,
        outs = [out],
        cmd = _build_image_values_cmd(images, out),
        tools = ["@multitool//tools/jq"],
    )
```

> **Note on jq vs Python/Go:** For the actual implementation, a small shell script or `genrule` that calls `jq` (already in the toolchain as `@jq_toolchains`) is sufficient. Dot-path expansion (e.g. `"api.image"` → `{api: {image: …}}`) is a known jq pattern. An alternative is a simple Python script checked into `tools/` if the jq expression becomes unwieldy.

**Generated output for a single-image chart:**

```yaml
image:
  repository: ghcr.io/jomcgi/homelab/charts/todo
  tag: "sha256:3f2e1a4b8c9d..."
```

**Generated output for a multi-image chart:**

```yaml
api:
  image:
    repository: ghcr.io/jomcgi/homelab/services/trips/api
    tag: "sha256:abc123..."
imgproxy:
  image:
    repository: ghcr.io/jomcgi/homelab/services/trips/imgproxy
    tag: "sha256:def456..."
```

### Component 3: Integration with `helm_chart` and `argocd_app`

#### In `helm_chart` (for testing and packaging)

Add an optional `image_values` attribute to the `helm_chart` macro:

```starlark
def helm_chart(
    name,
    publish = False,
    image_values = None,   # NEW: label of a helm_image_values target
    repository = "oci://ghcr.io/jomcgi/homelab/charts",
    ...):
    ...
    if image_values:
        helm_lint_test(
            name = "lint_test",
            extra_values = [image_values],  # pass generated values to lint
            ...
        )
        if publish:
            helm_package(
                name = name + ".package",
                srcs = native.glob(["**/*"]),
                image_values = image_values,  # embed as a bundled values layer
                ...
            )
```

When `image_values` is set, the packaged chart `.tgz` includes the generated values fragment as `values.image-generated.yaml`, providing a self-contained reference to what image versions were tested against when the chart was built.

#### In `argocd_app` / `helm_template_test` (for overlay testing)

Overlays can optionally reference the image values for template testing:

```starlark
# overlays/prod/todo/BUILD
argocd_app(
    name = "todo",
    chart = "charts/todo",
    chart_files = "//charts/todo:chart",
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
        "//charts/todo:image_values",  # NEW: build-time image values
    ],
)
```

This ensures `helm template` tests use the exact image digest that Bazel would deploy, catching any mismatch between chart templates and image labels at CI time.

---

## Example `BUILD.bazel` Wiring

### Before (current state — no Bazel connection)

```starlark
# charts/todo/BUILD
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    publish = True,
    visibility = ["//overlays/prod/todo:__pkg__"],
)
```

```starlark
# charts/todo/image/BUILD
load("//tools/oci:apko_image.bzl", "apko_image")

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@todo_lock//:contents",
    multiarch_tars = [":binary_tar"],
    repository = "ghcr.io/jomcgi/homelab/charts/todo",  # duplicated in values.yaml
    tars = [":static_tar"],
)
```

```yaml
# charts/todo/values.yaml
image:
  repository: ghcr.io/jomcgi/homelab/charts/todo  # duplicated from BUILD
  tag: main                                         # managed by ArgoCD Image Updater
```

### After (with Bazel image wiring)

```starlark
# charts/todo/image/BUILD
load("//tools/oci:apko_image.bzl", "apko_image")

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@todo_lock//:contents",
    multiarch_tars = [":binary_tar"],
    repository = "ghcr.io/jomcgi/homelab/charts/todo",
    tars = [":static_tar"],
    # Now emits :image.repository and :image.digest as build artifacts
)
```

```starlark
# charts/todo/BUILD
load("//rules_helm:defs.bzl", "helm_chart", "helm_image_values")

helm_image_values(
    name = "image_values",
    images = {
        "image": "//charts/todo/image:image",
    },
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
  repository: ""   # now populated by Bazel from :image_values; leave blank or omit
  tag: ""          # same — driven by build graph, not manually maintained
```

```starlark
# overlays/prod/todo/BUILD
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "todo",
    chart = "charts/todo",
    chart_files = "//charts/todo:chart",
    namespace = "prod",
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
        "//charts/todo:image_values",  # build-time image digest
    ],
)
```

---

## How Digests Flow

```
Source code changes
       │
       ▼
 go_binary / apko_image
  (Bazel build action)
       │
       ├─► :image              (OCI image directory in Bazel sandbox)
       │
       ├─► :image.digest       (sha256:abc... — build-time, content-addressed)
       │                        ← THIS is the hermetic anchor
       └─► :image.repository   (ghcr.io/jomcgi/homelab/charts/todo)
                │                 (new, from Component 1)
                │
                ▼
        helm_image_values
         (genrule / jq)
                │
                ▼
         image_values.yaml
         ┌─────────────────────────────────────────┐
         │  image:                                  │
         │    repository: ghcr.io/…/charts/todo     │
         │    tag: "sha256:abc..."                  │
         └─────────────────────────────────────────┘
                │
       ┌────────┴──────────────┐
       ▼                       ▼
helm_lint_test           helm_package
(uses digest values      (embeds values fragment
 for template test)       in .tgz for audit)
                               │
                               ▼
                        helm_push → OCI chart registry
                        (chart version tied to image digest)
```

At **runtime**, ArgoCD Image Updater still watches the registry tag for live rollout updates. The Bazel-generated digest is the *initial* anchor and the source for CI testing — Image Updater continues to handle the continuous delivery loop.

---

## Alternatives Considered

### Alt A: Stamp-based tag injection (not recommended as primary)

Use `expand_template` with `STABLE_IMAGE_TAG` to inject the timestamp+SHA tag into a generated values file. This is what the existing `{name}_stamped_tags_ci.txt` files do.

**Rejected because:** Stamp variables change on every commit (they include git SHA and timestamp), so every build produces a different tag even if source code hasn't changed. This makes CI caching less effective and doesn't provide true hermeticity — the digest approach is strictly better.

**Still useful for:** The `remote_tags` files passed to `oci_push` (current use is correct and unchanged).

### Alt B: `helm_release` rule (deploy-time wiring)

A rule that generates a complete `helm upgrade --install` invocation, calling push, capturing the digest, and templating it into `--set` overrides at run time.

**Rejected because:** This would require network access during Bazel actions (to push the image and get the registry-assigned digest), breaking hermeticity and remote execution compatibility. It also doesn't integrate with ArgoCD's GitOps pull model.

### Alt C: OCI annotation on chart (chart carries image reference)

Embed the image reference as an OCI annotation in the Helm chart's `Chart.yaml`:
```yaml
annotations:
  org.opencontainers.image.source: "ghcr.io/jomcgi/homelab/charts/todo@sha256:..."
```

**Rejected as primary** but worth doing as a complement: it's useful for auditability but doesn't affect how Helm deploys the chart (ArgoCD reads `values.yaml`, not chart annotations).

### Alt D: Single `helm_oci_chart` rule (full replacement)

Replace `helm_chart` + `go_image` with a unified rule that takes Go source and chart templates together.

**Rejected because:** Too opinionated; couples image build strategy to chart packaging. The current separation of concerns (image BUILD in `charts/<svc>/image/`, chart in `charts/<svc>/`) is clean and should be preserved.

---

## Limitations and Open Questions

### 1. Build-time vs. registry digest

The `.digest` target from `rules_oci` reflects the **local build digest** — computed from the OCI layer contents in Bazel's sandbox. This matches the digest the image will have in the registry **if pushed with `oci_push`** (content-addressed OCI push is deterministic). However, if a registry transforms the image (e.g. recompression), the registry digest may differ. In practice, GHCR does not transform layers, so this is not a concern for this repo.

### 2. Multi-image charts

Charts like `trips` that deploy multiple images (API server, imgproxy) require entries for each image. The `helm_image_values` rule handles this via the `images` dict, but each image target must emit its own `.repository` file.

### 3. ArgoCD Image Updater coexistence

After adopting this design:
- The `image.repository` value in `values.yaml` can be removed (left empty or set to the canonical default).
- The `image.tag` value will be set by both `helm_image_values` (build-time digest) and ArgoCD Image Updater (runtime digest).
- ArgoCD Image Updater's write-back will continue to override `image.tag` in the overlay `values.yaml` — this is intentional and desirable for live updates.
- The Bazel-generated values can be used for CI template testing without needing a live cluster.

### 4. Overlay values override order

The proposed `values_files` ordering in `argocd_app` puts `image_values` **after** the base `values.yaml` but the overlay `values.yaml` should still come last so human-authored overrides win. Suggested order:

```
1. charts/<svc>/values.yaml       (chart defaults, no image ref)
2. charts/<svc>:image_values      (Bazel-generated digest values)
3. overlays/<env>/<svc>/values.yaml  (ArgoCD Image Updater writes here; wins at runtime)
```

### 5. `values.yaml` migration

Existing `charts/<svc>/values.yaml` files have `image.repository` hardcoded. Adopting this design requires removing those values (or leaving them as documentation comments) once the `helm_image_values` rule is in place. This is a one-time migration per chart.

---

## Implementation Plan

The design is decomposed into three independent, reviewable pieces:

| Step | File(s) | Effort |
|---|---|---|
| **1** | `tools/oci/go_image.bzl` + `apko_image.bzl` — emit `{name}.repository` file | Small (2 lines per macro) |
| **2** | `rules_helm/image_values.bzl` — new `helm_image_values` rule | Medium (new rule + tests) |
| **3** | `rules_helm/chart.bzl` — add `image_values` attr to `helm_chart` | Small |
| **4** | `rules_helm/defs.bzl` — export `helm_image_values` | Trivial |
| **5** | `rules_helm/test.bzl` — thread `image_values` into `helm_lint_test` | Small |
| **6** | Pilot on one chart (e.g. `charts/todo`) | Medium (includes migration) |
| **7** | Roll out to other first-party charts | Mechanical |

Start with Steps 1–4 as a single PR, then pilot on `charts/todo` separately.

---

## Summary

| Concern | Current | Proposed |
|---|---|---|
| Image repo source of truth | Duplicated in BUILD + `values.yaml` | BUILD file only (via `.repository` file) |
| Image tag source of truth | ArgoCD Image Updater writes `values.yaml` | Bazel digest at CI/build time; Image Updater for live updates |
| `helm template` test accuracy | Uses static tag, not real digest | Uses build-time digest from `.digest` target |
| Hermeticity | No link between chart and image builds | Full Bazel dep graph: source → digest → values → chart |
| New rule surface area | — | `helm_image_values` + `{name}.repository` file per image |
| ArgoCD compatibility | ✓ | ✓ (unchanged) |
