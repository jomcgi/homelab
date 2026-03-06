load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Goose config into the image at ~/.config/goose/config.yaml
pkg_tar(
    name = "config_tar",
    srcs = ["config.yaml"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/.config/goose",
)

# Build the goose-agent image:
#   apko base: bash, git, gh, go, node, pnpm (from Wolfi)
#   multiarch tars: goose binary, bb (BuildBuddy CLI)
#   regular tars: Goose config
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@goose_agent_lock//:contents",
    multiarch_tars = [
        "@goose//:tar",
        "@bb//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/goose-agent",
    tars = [":config_tar"],
)
