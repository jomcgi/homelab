load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_push")
load("@tar_bzl//tar:tar.bzl", "tar")

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

# Package the binary into a tar layer for the container
pkg_tar(
    name = "backend_layer",
    srcs = [":backend"],
    package_dir = "/app",
    mode = "0755",
)

oci_image(
    name = "image",
    base = "@alpine_linux_amd64",
    entrypoint = ["/app/backend"],
    tars = [":backend_layer"],
    exposed_ports = ["8080/tcp"],
    user = "1000",
)

oci_push(
    name = "push",
    image = ":image",
    repository = "ghcr.io/jomcgi/ttyd-session-manager",
    remote_tags = ["latest"],
)
