load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "cluster-ingress",
    chart = "projects/platform/cloudflare/tunnel",
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
