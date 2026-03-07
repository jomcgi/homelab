load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "goose-sandboxes",
    chart = "charts/goose-sandboxes",
    chart_files = "//charts/goose-sandboxes:chart",
    namespace = "goose-sandboxes",
    release_name = "goose-sandboxes",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/goose-sandboxes:values.yaml",
        "values.yaml",
    ],
)
