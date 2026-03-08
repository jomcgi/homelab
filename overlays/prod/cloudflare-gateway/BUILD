load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cloudflare-gateway",
    chart = "charts/cloudflare-gateway",
    chart_files = "//charts/cloudflare-gateway:chart",
    namespace = "gateway",
    release_name = "cloudflare-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-gateway:values.yaml",
        "values.yaml",
    ],
)
