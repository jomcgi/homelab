load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "argocd",
    chart = "charts/argocd",
    chart_files = "//charts/argocd:chart",
    namespace = "argocd",
    release_name = "argocd",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/argocd:values.yaml",
        "//clusters/homelab/argocd:values.yaml",
    ],
)
