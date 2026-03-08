load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "grimoire",
    chart = "charts/grimoire",
    chart_files = "//charts/grimoire:chart",
    namespace = "grimoire",
    release_name = "grimoire",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/grimoire:values.yaml",
        "values.yaml",
    ],
)
