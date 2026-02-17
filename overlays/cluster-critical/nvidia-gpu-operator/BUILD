load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "nvidia-gpu-operator",
    chart = "charts/nvidia-gpu-operator",
    chart_files = "//charts/nvidia-gpu-operator:chart",
    namespace = "gpu-operator",
    release_name = "nvidia-gpu-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = ["//charts/nvidia-gpu-operator:values.yaml"],
)
