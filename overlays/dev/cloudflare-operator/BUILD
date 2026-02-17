load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cloudflare-operator",
    chart = "operators/cloudflare/helm/cloudflare-operator",
    chart_files = "//operators/cloudflare/helm/cloudflare-operator:chart",
    namespace = "cloudflare",
    release_name = "cloudflare-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//operators/cloudflare/helm/cloudflare-operator:values.yaml",
        "values.yaml",
    ],
)
