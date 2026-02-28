load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "context-forge",
    chart = "charts/context-forge",
    chart_files = "//charts/context-forge:chart",
    namespace = "mcp-gateway",
    release_name = "context-forge",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/context-forge:values.yaml",
        "values.yaml",
    ],
)
