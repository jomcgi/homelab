load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "argocd-image-updater",
    chart = "charts/argocd-image-updater",
    chart_files = "//charts/argocd-image-updater:chart",
    namespace = "argocd",
    release_name = "argocd-image-updater",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/argocd-image-updater:values.yaml",
        "values.yaml",
    ],
)
