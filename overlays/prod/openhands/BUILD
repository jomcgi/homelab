load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "openhands",
    chart = "charts/openhands",
    chart_files = "//charts/openhands:chart",
    namespace = "openhands",
    release_name = "openhands",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/openhands:values.yaml",
        "values.yaml",
    ],
)
