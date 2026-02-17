load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "prod-llama-cpp",
    chart = "charts/llama-cpp",
    chart_files = "//charts/llama-cpp:chart",
    namespace = "llama-cpp",
    release_name = "llama-cpp",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/llama-cpp:values.yaml",
        "values.yaml",
    ],
)
