load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package start.sh and package.json at /app/
pkg_tar(
    name = "app_base_tar",
    srcs = [
        "start.sh",
        "//charts/claude/src:package.json",
    ],
    mode = "0755",
    owner = "1000.1000",
    package_dir = "app",
)

# Package the compiled TypeScript at /app/dist/
pkg_tar(
    name = "app_dist_tar",
    srcs = ["//charts/claude/src:dist"],
    mode = "0755",
    owner = "1000.1000",
    package_dir = "app/dist",
)

# Package the compiled frontend at /app/public/
pkg_tar(
    name = "frontend_tar",
    srcs = ["//charts/claude/frontend:dist"],
    mode = "0644",
    owner = "1000.1000",
    package_dir = "app/public",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@claude_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/claude",
    tars = [
        ":app_base_tar",
        ":app_dist_tar",
        ":frontend_tar",
    ],
)
