load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "vaultMcp.image": "//projects/obsidian_vault/image:image.info",
    },
    publish = True,
)
