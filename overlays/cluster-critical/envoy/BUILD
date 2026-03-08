load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "envoy-gateway",
    chart = "charts/envoy-gateway",
    chart_files = "//charts/envoy-gateway:chart",
    namespace = "envoy-gateway-system",
    release_name = "envoy-gateway",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/envoy-gateway:values.yaml",
        "values.yaml",
    ],
)
