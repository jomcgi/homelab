load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Package the Go binary for amd64
platform_transition_filegroup(
    name = "binary_amd64",
    srcs = ["//projects/todo_app/cmd"],
    target_platform = "@rules_go//go/toolchain:linux_amd64",
)

tar(
    name = "binary_tar_amd64",
    srcs = [":binary_amd64"],
    mtree = ["./opt/app type=file content=$(execpath :binary_amd64)"],
)

# Package the Go binary for arm64
platform_transition_filegroup(
    name = "binary_arm64",
    srcs = ["//projects/todo_app/cmd"],
    target_platform = "@rules_go//go/toolchain:linux_arm64",
)

tar(
    name = "binary_tar_arm64",
    srcs = [":binary_arm64"],
    mtree = ["./opt/app type=file content=$(execpath :binary_arm64)"],
)

# Package static files
pkg_tar(
    name = "static_tar",
    srcs = ["//projects/todo_app:static_files"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/app/static",
    strip_prefix = "projects/todo_app/static",
)

# Build the image with apko base + binary + static files
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@todo_lock//:contents",
    multiarch_tars = [":binary_tar"],
    repository = "ghcr.io/jomcgi/homelab/projects/todo_app/image",
    tars = [":static_tar"],
)
