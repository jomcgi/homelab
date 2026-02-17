load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cluster-ingress",
    chart = "charts/cloudflare-tunnel",
    chart_files = "//charts/cloudflare-tunnel:chart",
    namespace = "ingress",
    release_name = "cluster-ingress",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-tunnel:values.yaml",
        "values.yaml",
    ],
)
