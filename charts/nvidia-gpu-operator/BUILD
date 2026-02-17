load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/cluster-critical/nvidia-gpu-operator:__pkg__"],
)
