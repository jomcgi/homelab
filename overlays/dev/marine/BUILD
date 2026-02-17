load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "marine",
    chart = "charts/marine",
    chart_files = "//charts/marine:chart",
    namespace = "marine",
    release_name = "marine",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/marine:values.yaml",
        "values.yaml",
    ],
)
