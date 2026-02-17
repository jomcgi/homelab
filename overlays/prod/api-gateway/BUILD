load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "api-gateway",
    chart = "charts/api-gateway",
    chart_files = "//charts/api-gateway:chart",
    namespace = "api-gateway",
    release_name = "api-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/api-gateway:values.yaml",
        "values.yaml",
    ],
)
