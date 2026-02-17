load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "gh-arc-controller",
    chart = "charts/gh-arc-controller",
    chart_files = "//charts/gh-arc-controller:chart",
    namespace = "gh-arc-controller",
    release_name = "gh-arc-controller",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/gh-arc-controller:values.yaml",
        "values.yaml",
    ],
)
