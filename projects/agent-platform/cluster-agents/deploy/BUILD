load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "cluster-agents",
    chart = "projects/agent-platform/cluster-agents/deploy",
    chart_files = ":chart",
    namespace = "cluster-agents",
    release_name = "cluster-agents",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
