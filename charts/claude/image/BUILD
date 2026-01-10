load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the compiled TypeScript API server
pkg_tar(
    name = "app_tar",
    srcs = glob(["../src/dist/**/*"]) + [
        "../src/package.json",
        "start.sh",
    ],
    mode = "0755",
    remap_paths = {
        "../src/dist": "/app/dist",
        "../src/package.json": "/app/package.json",
        "start.sh": "/app/start.sh",
    },
)

# Package the compiled frontend
pkg_tar(
    name = "frontend_tar",
    srcs = glob(["../frontend/dist/**/*"]),
    mode = "0644",
    remap_paths = {
        "../frontend/dist": "/app/public",
    },
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@claude_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/claude",
    tars = [
        ":app_tar",
        ":frontend_tar",
    ],
)
