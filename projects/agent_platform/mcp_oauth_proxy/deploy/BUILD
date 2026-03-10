load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "mcp-oauth-proxy",
    chart = "projects/agent_platform/mcp_oauth_proxy/deploy",
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
