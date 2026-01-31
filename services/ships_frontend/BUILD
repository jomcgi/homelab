load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Bun server
pkg_tar(
    name = "server_tar",
    srcs = ["server.ts"],
    mode = "0755",
    owner = "65532.65532",
    package_dir = "app",
)

# Package the pre-built website dist
# Built during CI by //websites/ships.jomcgi.dev:build (vite build)
pkg_tar(
    name = "dist_tar",
    srcs = ["//websites/ships.jomcgi.dev:dist"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/public",
    strip_prefix = "websites/ships.jomcgi.dev/dist",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@ships_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/services/ships_frontend",
    tars = [
        ":server_tar",
        ":dist_tar",
    ],
)

py_library(
    name = "ships_frontend",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)
