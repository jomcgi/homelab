load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Package the Bun server
pkg_tar(
    name = "server_tar",
    srcs = ["server.ts"],
    mode = "0755",
    owner = "65532.65532",
    package_dir = "app",
)

# Package the pre-built website dist
# Built during CI by //projects/ships/frontend/web:build (vite build)
pkg_tar(
    name = "dist_tar",
    srcs = ["//projects/ships/frontend/web:dist"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/public",
    strip_prefix = "projects/ships/frontend/web/dist",
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

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
