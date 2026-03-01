load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "mcp-servers",
    chart = "charts/mcp-servers",
    chart_files = "//charts/mcp-servers:chart",
    namespace = "mcp-servers",
    release_name = "mcp-servers",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/mcp-servers:values.yaml",
        "values.yaml",
    ],
)
