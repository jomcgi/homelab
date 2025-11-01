load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:apko_image.bzl", "apko_image")
load("//tools/oci:go_image.bzl", "go_image")

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

# TTYD worker image with fish shell dev environment + ttyd binary + opencode
# multiarch_tars: platform-specific tars from multiarch_http_file and multiarch_http_archive repositories
apko_image(
    name = "ttyd_worker_image",
    config = "apko.yaml",
    contents = "@ttyd_lock//:contents",
    multiarch_tars = [
        "@ttyd//:tar",
        "@opencode//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker",
)
