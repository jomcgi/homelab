load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "cloudflare-operator-test",
    chart = "charts/cloudflare-operator-test",
    chart_files = "//charts/cloudflare-operator-test:chart",
    namespace = "cloudflare-operator-test",
    release_name = "cloudflare-operator-test",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/cloudflare-operator-test:values.yaml",
        "values.yaml",
    ],
)
