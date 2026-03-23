load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "vaultMcp.image": "//projects/obsidian_vault:py_image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
