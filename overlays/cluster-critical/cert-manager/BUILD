load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cert-manager",
    chart = "charts/cert-manager",
    chart_files = "//charts/cert-manager:chart",
    namespace = "cert-manager",
    release_name = "cert-manager",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cert-manager:values.yaml",
        "values.yaml",
    ],
)
