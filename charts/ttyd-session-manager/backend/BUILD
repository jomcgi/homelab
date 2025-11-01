load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:apko_image.bzl", "apko_image")
load("//tools/oci:go_image.bzl", "go_image")
load("//tools/oci:multiplatform_tar.bzl", "multiplatform_tar")

go_library(
    name = "backend_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/charts/ttyd-session-manager/backend",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_gin_gonic_gin//:go_default_library",
        "@com_github_google_uuid//:uuid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/resource",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
        "@io_k8s_client_go//tools/clientcmd",
    ],
)

go_binary(
    name = "backend",
    embed = [":backend_lib"],
    visibility = ["//visibility:public"],
)

# Backend API server image
go_image(
    name = "image",
    binary = "backend",
)

# Create platform-specific ttyd binary layers
ttyd_layers = multiplatform_tar(
    name = "ttyd_layer",
    amd64 = "@ttyd_amd64//file",
    arm64 = "@ttyd_aarch64//file",
    package_dir = "/usr/local/bin",
    remap_to = "ttyd",
)

# TTYD worker image with fish shell dev environment + ttyd binary
# The apko_image macro handles creating platform-specific base images,
# layering the platform-specific ttyd binaries, and combining into a multi-platform index
apko_image(
    name = "ttyd_worker_image",
    config = "apko.yaml",
    contents = "@ttyd_lock//:contents",
    multiplatform_tars = [ttyd_layers],
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker",
)
