load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "litellm",
    chart = "charts/litellm",
    chart_files = "//charts/litellm:chart",
    namespace = "litellm",
    release_name = "litellm",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/litellm:values.yaml",
        "values.yaml",
    ],
)
