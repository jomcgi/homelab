load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-nats",
    chart = "charts/nats",
    chart_files = "//charts/nats:chart",
    namespace = "nats",
    release_name = "nats",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/nats:values.yaml",
        "values.yaml",
    ],
)
