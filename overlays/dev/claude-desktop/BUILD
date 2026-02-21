load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "claude-desktop",
    chart = "charts/claude-desktop",
    chart_files = "//charts/claude-desktop:chart",
    namespace = "claude-desktop",
    release_name = "claude-desktop",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/claude-desktop:values.yaml",
        "values.yaml",
    ],
)
