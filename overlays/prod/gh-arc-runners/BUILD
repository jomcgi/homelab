load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "gh-arc-runners",
    chart = "charts/gh-arc-runners",
    chart_files = "//charts/gh-arc-runners:chart",
    namespace = "gh-arc-runners",
    release_name = "gh-arc-runners",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/gh-arc-runners:values.yaml",
        "values.yaml",
    ],
)
