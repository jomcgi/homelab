load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "todo",
    chart = "charts/todo",
    chart_files = "//charts/todo:chart",
    namespace = "todo",
    release_name = "todo",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/todo:values.yaml",
        "values.yaml",
    ],
)
