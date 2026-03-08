load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "signoz-dashboard-sidecar",
    chart = "charts/signoz-dashboard-sidecar",
    chart_files = "//charts/signoz-dashboard-sidecar:chart",
    namespace = "signoz",
    release_name = "signoz-dashboard-sidecar",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/signoz-dashboard-sidecar:values.yaml",
        "values.yaml",
    ],
)
