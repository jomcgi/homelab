load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/cluster-critical/argocd:__pkg__"],
)
