load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/prod/cloudflare-gateway:__pkg__"],
)
