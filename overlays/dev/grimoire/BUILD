load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "grimoire",
    chart = "projects/grimoire/deploy",
    chart_files = "//projects/grimoire/deploy:chart",
    namespace = "grimoire",
    release_name = "grimoire",
    tags = [
        "helm",
        "template",
    ],
    values_files = ["//projects/grimoire/deploy:values.yaml"],
)
