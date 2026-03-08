load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/prod/cloudflare-ingress:__pkg__"],
)
