load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Bun server
pkg_tar(
    name = "server_tar",
    srcs = [
        "server.ts",
        "start.sh",
    ],
    mode = "0755",
    owner = "65532.65532",
    package_dir = "app",
)

# Package the website source for runtime build
# Use strip_prefix="." to preserve directory structure from the source package
pkg_tar(
    name = "website_tar",
    srcs = ["//websites/ships.jomcgi.dev:src"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/website",
    strip_prefix = ".",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@ships_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/services/ships-frontend",
    tars = [
        ":server_tar",
        ":website_tar",
    ],
)
