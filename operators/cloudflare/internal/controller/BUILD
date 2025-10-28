load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "controller",
    srcs = ["cloudflaretunnel_controller.go"],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/internal/controller",
    visibility = ["//operators/cloudflare:__subpackages__"],
    deps = [
        "//operators/cloudflare/api/v1:api",
        "//operators/cloudflare/internal/cloudflare",
        "//operators/cloudflare/internal/telemetry",
        "@io_k8s_api//apps/v1:go_default_library",
        "@io_k8s_apimachinery//pkg/api/errors:go_default_library",
        "@io_k8s_apimachinery//pkg/api/meta:go_default_library",
        "@io_k8s_apimachinery//pkg/runtime:go_default_library",
        "@io_k8s_apimachinery//pkg/types:go_default_library",
        "@io_k8s_client_go//util/workqueue:go_default_library",
    ],
)

go_test(
    name = "controller_test",
    srcs = [
        "cloudflaretunnel_controller_test.go",
        "suite_test.go",
    ],
    embed = [":controller"],
    deps = [
        "//operators/cloudflare/api/v1:api",
        "//operators/cloudflare/internal/cloudflare",
        "@io_k8s_apimachinery//pkg/api/errors:go_default_library",
        "@io_k8s_apimachinery//pkg/api/meta:go_default_library",
        "@io_k8s_apimachinery//pkg/types:go_default_library",
        "@io_k8s_client_go//rest:go_default_library",
    ],
)
