load("//tools/argocd:defs.bzl", "helm_render")

helm_render(
    name = "bazel-cache-seeder",
    chart = "bazel-cache-seeder",
    output_filename = "bazel-cache-seeder-manifests.yaml",
    release_name = "bazel-cache-seeder",
)
