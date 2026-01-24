load("//tools/argocd:defs.bzl", "helm_application")

helm_application(
    name = "manifests",
    chart = "//charts/signoz-dashboard-sidecar:all_files",
    namespace = "signoz",
    release_name = "signoz-dashboard-sidecar",
    values_files = [
        "//charts/signoz-dashboard-sidecar:values.yaml",
        "values.yaml",
    ],
)
