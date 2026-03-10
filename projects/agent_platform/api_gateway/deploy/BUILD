load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "api-gateway",
    chart = "projects/agent_platform/api_gateway/deploy",
    chart_files = ":chart",
    namespace = "api-gateway",
    release_name = "api-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
