load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-trips",
    chart = "charts/trips",
    chart_files = "//charts/trips:chart",
    namespace = "trips",
    release_name = "trips",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/trips:values.yaml",
        "values.yaml",
    ],
)
