load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-seaweedfs",
    chart = "charts/seaweedfs",
    chart_files = "//charts/seaweedfs:chart",
    namespace = "seaweedfs",
    release_name = "seaweedfs",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/seaweedfs:values.yaml",
        "values.yaml",
    ],
)
