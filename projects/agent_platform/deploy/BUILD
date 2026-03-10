load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
