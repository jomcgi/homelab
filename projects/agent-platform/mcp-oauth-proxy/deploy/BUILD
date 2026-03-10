load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "mcp-oauth-proxy",
    chart = "projects/agent-platform/mcp-oauth-proxy/deploy",
    chart_files = ":chart",
    namespace = "mcp-gateway",
    release_name = "mcp-oauth-proxy",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
