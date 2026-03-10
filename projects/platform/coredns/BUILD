load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "coredns-config",
    chart = "projects/platform/coredns/deploy",
    chart_files = ":chart",
    namespace = "kube-system",
    release_name = "coredns",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
