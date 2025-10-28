load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cmd_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/cmd",
    visibility = ["//visibility:private"],
    deps = [
        "//operators/cloudflare/api/v1:api",
        "//operators/cloudflare/internal/cloudflare",
        "//operators/cloudflare/internal/controller",
        "//operators/cloudflare/internal/telemetry",
        "@io_k8s_apimachinery//pkg/runtime:go_default_library",
        "@io_k8s_apimachinery//pkg/util/runtime:go_default_library",
    ],
)

go_binary(
    name = "cmd",
    embed = [":cmd_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = "cmd",
)
