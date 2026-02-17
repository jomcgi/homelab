load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-openclaw-personal",
    chart = "charts/openclaw",
    chart_files = "//charts/openclaw:chart",
    namespace = "openclaw",
    release_name = "openclaw-personal",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/openclaw:values.yaml",
        "values.yaml",
    ],
)
