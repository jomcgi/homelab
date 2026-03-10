load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "coredns-config",
    chart = "projects/platform/coredns",
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
