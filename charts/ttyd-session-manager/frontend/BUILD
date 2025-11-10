load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package frontend static files
pkg_tar(
    name = "frontend_files_tar",
    srcs = [
        "index.html",
    ],
    mode = "0644",
    package_dir = "/usr/share/nginx/html",
)

# Package nginx configuration
pkg_tar(
    name = "nginx_config_tar",
    srcs = [
        "default.conf",
    ],
    mode = "0644",
    package_dir = "/etc/nginx/conf.d",
)

# Frontend nginx image with static files
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/frontend",
    tars = [
        ":frontend_files_tar",
        ":nginx_config_tar",
    ],
)
