load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "claude",
    chart = "charts/claude",
    chart_files = "//charts/claude:chart",
    namespace = "claude",
    release_name = "claude",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/claude:values.yaml",
        "values.yaml",
    ],
)
