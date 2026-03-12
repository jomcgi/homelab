load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/platform/signoz-addons/dashboard-sidecar/cmd:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "signoz-dashboard-sidecar",
    chart = "projects/platform/signoz-addons/dashboard-sidecar",
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
