load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "mcp-oauth-proxy",
    chart = "charts/mcp-oauth-proxy",
    chart_files = "//charts/mcp-oauth-proxy:chart",
    namespace = "mcp-gateway",
    release_name = "mcp-oauth-proxy",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/mcp-oauth-proxy:values.yaml",
        "values.yaml",
    ],
)
