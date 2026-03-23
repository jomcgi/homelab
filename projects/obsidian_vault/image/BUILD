load("//bazel/tools/oci:apko_image.bzl", "apko_image")

package(default_visibility = ["//projects/obsidian_vault:__subpackages__"])

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/obsidian_vault/image",
)
