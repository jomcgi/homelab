load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "stargazer",
    chart = "charts/stargazer",
    chart_files = "//charts/stargazer:chart",
    namespace = "stargazer",
    release_name = "stargazer",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/stargazer:values.yaml",
        "values.yaml",
    ],
)
