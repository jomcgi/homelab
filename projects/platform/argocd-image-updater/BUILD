load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "argocd-image-updater",
    chart = "projects/platform/argocd-image-updater",
    chart_files = ":chart",
    namespace = "argocd",
    release_name = "argocd-image-updater",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
