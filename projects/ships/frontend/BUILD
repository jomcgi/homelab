load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_pkg//pkg:mappings.bzl", "REMOVE_BASE_DIRECTORY", "pkg_files")
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

# Map the Vite build output (TreeArtifact) to flat paths under app/public.
# pkg_tar's strip_prefix doesn't work with TreeArtifacts from js_run_binary,
# so we use pkg_files with REMOVE_BASE_DIRECTORY to strip the directory structure.
pkg_files(
    name = "dist_files",
    srcs = ["//projects/ships/frontend/web:dist"],
    renames = {"//projects/ships/frontend/web:dist": REMOVE_BASE_DIRECTORY},
    prefix = "app/public",
)

pkg_tar(
    name = "dist_tar",
    deps = [":dist_files"],
    mode = "0644",
    owner = "65532.65532",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@ships_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/ships/frontend",
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
