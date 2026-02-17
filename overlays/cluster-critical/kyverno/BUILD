load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "kyverno",
    chart = "charts/kyverno",
    chart_files = "//charts/kyverno:chart",
    namespace = "kyverno",
    release_name = "kyverno",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/kyverno:values.yaml",
        "values.yaml",
    ],
)
