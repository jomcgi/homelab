load("//bazel/helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cloudflare-ingress",
    chart = "charts/cloudflare-ingress",
    chart_files = "//charts/cloudflare-ingress:chart",
    namespace = "envoy-gateway-system",
    release_name = "cloudflare-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-ingress:values.yaml",
        "values.yaml",
    ],
)
