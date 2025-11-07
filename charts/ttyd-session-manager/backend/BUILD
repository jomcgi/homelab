load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "backend_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/charts/ttyd-session-manager/backend",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_gin_gonic_gin//:gin",
        "@com_github_google_uuid//:uuid",
        "@com_github_gorilla_websocket//:go_default_library",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/resource",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
        "@io_k8s_client_go//tools/clientcmd",
        "@io_k8s_metrics//pkg/client/clientset/versioned:go_default_library",
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

# Fish shell configuration files for Bazel setup and terminal config
pkg_tar(
    name = "fish_config_tar",
    srcs = [
        "bazel.fish",
        "setup-bazelrc.fish",
        "terminal.fish",
    ],
    mode = "0755",
    remap_paths = {
        "bazel.fish": "/home/user/.config/fish/conf.d/bazel.fish",
        "setup-bazelrc.fish": "/usr/local/bin/setup-bazelrc.fish",
        "terminal.fish": "/home/user/.config/fish/conf.d/terminal.fish",
    },
)

# OpenCode configuration for vLLM and provider access
pkg_tar(
    name = "opencode_config_tar",
    srcs = [
        "opencode-config.json",
    ],
    mode = "0644",
    remap_paths = {
        "opencode-config.json": "/home/user/.config/opencode/opencode.json",
    },
)

# TTYD worker image with fish shell dev environment + ttyd binary + opencode
# multiarch_tars: platform-specific tars from multiarch_http_file and multiarch_http_archive repositories
# Note: format tool available via bazelisk (already in image), run with: bazel run //tools/format:format
apko_image(
    name = "ttyd_worker_image",
    config = "apko.yaml",
    contents = "@ttyd_lock//:contents",
    multiarch_tars = [
        "@ttyd//:tar",
        "@opencode//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker",
    tars = [
        ":fish_config_tar",
        ":opencode_config_tar",
    ],
)
