load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "bosun",
    chart = "charts/bosun",
    chart_files = "//charts/bosun:chart",
    namespace = "bosun",
    release_name = "bosun",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/bosun:values.yaml",
        "values.yaml",
    ],
)
