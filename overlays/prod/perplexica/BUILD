load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-perplexica",
    chart = "charts/perplexica",
    chart_files = "//charts/perplexica:chart",
    namespace = "search",
    release_name = "perplexica",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/perplexica:values.yaml",
        "values.yaml",
    ],
)
