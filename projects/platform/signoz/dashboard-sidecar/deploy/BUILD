load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    visibility = [":__pkg__"],
)

argocd_app(
    name = "signoz-dashboard-sidecar",
    chart = "projects/platform/signoz/dashboard-sidecar/deploy",
    chart_files = ":chart",
    namespace = "signoz",
    release_name = "signoz-dashboard-sidecar",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
