load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "knowledge-graph",
    chart = "charts/knowledge-graph",
    chart_files = "//charts/knowledge-graph:chart",
    namespace = "knowledge-graph",
    release_name = "knowledge-graph",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/knowledge-graph:values.yaml",
        "values.yaml",
    ],
)
