load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//projects:__subpackages__"],
)

argocd_app(
    name = "envoy-gateway",
    chart = "projects/platform/envoy-gateway",
    chart_files = ":chart",
    namespace = "envoy-gateway-system",
    release_name = "envoy-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
