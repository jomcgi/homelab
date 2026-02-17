load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "signoz",
    chart = "charts/signoz",
    chart_files = "//charts/signoz:chart",
    namespace = "signoz",
    release_name = "signoz",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/signoz:values.yaml",
        "values.yaml",
    ],
)
