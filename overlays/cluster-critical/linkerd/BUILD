load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "linkerd",
    chart = "charts/linkerd",
    chart_files = "//charts/linkerd:chart",
    namespace = "linkerd",
    release_name = "linkerd",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/linkerd:values.yaml",
        "values.yaml",
    ],
)
