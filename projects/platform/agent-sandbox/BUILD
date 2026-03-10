load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "agent-sandbox",
    chart = "projects/platform/agent-sandbox",
    chart_files = ":chart",
    namespace = "agent-sandbox-system",
    release_name = "agent-sandbox",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
