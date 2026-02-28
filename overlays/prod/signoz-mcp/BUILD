load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "signoz-mcp",
    chart = "charts/signoz-mcp",
    chart_files = "//charts/signoz-mcp:chart",
    namespace = "mcp-servers",
    release_name = "signoz-mcp",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/signoz-mcp:values.yaml",
        "values.yaml",
    ],
)
