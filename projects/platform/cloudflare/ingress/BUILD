load("//bazel/helm:defs.bzl", "argocd_app", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "cloudflare-ingress",
    chart = "projects/platform/cloudflare/ingress",
    chart_files = ":chart",
    namespace = "envoy-gateway-system",
    release_name = "cloudflare-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
        "values-prod.yaml",
    ],
)
