load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = [":__pkg__"],
)

argocd_app(
    name = "linkerd",
    chart = "projects/platform/linkerd/deploy",
    chart_files = ":chart",
    namespace = "linkerd",
    release_name = "linkerd",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
