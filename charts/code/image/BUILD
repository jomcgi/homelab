load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Fish shell configuration for PATH setup
pkg_tar(
    name = "fish_config_tar",
    srcs = [
        "config.fish",
    ],
    mode = "0644",
    remap_paths = {
        "config.fish": "/home/user/.config/fish/config.fish",
    },
)

# Code workspace image with opencode binary
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@code_lock//:contents",
    multiarch_tars = [
        "@opencode//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/charts/code/workspace",
    tars = [
        ":fish_config_tar",
    ],
)
