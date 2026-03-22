load("//bazel/tools/oci:apko_image.bzl", "apko_image")

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/obsidian_vault/image",
)
