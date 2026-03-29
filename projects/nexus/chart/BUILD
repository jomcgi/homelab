load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "backend.image": "//projects/nexus/backend:image.info",
    },
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
