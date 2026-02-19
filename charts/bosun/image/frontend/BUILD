"Bosun frontend: nginx serving pre-built React app"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@rules_oci//oci:defs.bzl", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the pre-built Vite dist into nginx html directory
pkg_tar(
    name = "dist_tar",
    srcs = ["//charts/bosun/frontend:dist"],
    mode = "0755",
    owner = "101.101",
    package_dir = "usr/share/nginx/html",
    strip_prefix = "charts/bosun/frontend/dist",
)

# Package the default nginx.conf (overridden by ConfigMap in k8s)
pkg_tar(
    name = "nginx_conf_tar",
    srcs = ["nginx.conf"],
    mode = "0644",
    owner = "101.101",
    package_dir = "etc/nginx",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@bosun_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/bosun/frontend",
    tars = [
        ":dist_tar",
        ":nginx_conf_tar",
    ],
)
