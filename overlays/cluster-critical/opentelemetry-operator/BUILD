load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "opentelemetry-operator",
    chart = "charts/opentelemetry-operator",
    chart_files = "//charts/opentelemetry-operator:chart",
    namespace = "opentelemetry-operator",
    release_name = "opentelemetry-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/opentelemetry-operator:values.yaml",
        "values.yaml",
    ],
)
