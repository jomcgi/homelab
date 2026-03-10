load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "cluster-ingress",
    chart = "projects/platform/cloudflare/tunnel/deploy",
    chart_files = ":chart",
    namespace = "ingress",
    release_name = "cluster-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
