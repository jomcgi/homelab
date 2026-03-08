load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cluster-agents",
    chart = "charts/cluster-agents",
    chart_files = "//charts/cluster-agents:chart",
    namespace = "cluster-agents",
    release_name = "cluster-agents",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cluster-agents:values.yaml",
        "values.yaml",
    ],
)
