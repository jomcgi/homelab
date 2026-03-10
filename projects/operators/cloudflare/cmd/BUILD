load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "cmd_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/projects/operators/cloudflare/cmd",
    visibility = ["//visibility:private"],
    deps = [
        "//projects/operators/cloudflare/api/v1:api",
        "//projects/operators/cloudflare/internal/cloudflare",
        "//projects/operators/cloudflare/internal/controller",
        "//projects/operators/cloudflare/internal/statemachine",
        "//projects/operators/cloudflare/internal/telemetry",
        "@io_k8s_apimachinery//pkg/runtime",
        "@io_k8s_apimachinery//pkg/util/runtime",
        "@io_k8s_client_go//kubernetes/scheme",
        "@io_k8s_client_go//plugin/pkg/client/auth",
        "@io_k8s_sigs_controller_runtime//:controller-runtime",
        "@io_k8s_sigs_controller_runtime//pkg/certwatcher",
        "@io_k8s_sigs_controller_runtime//pkg/healthz",
        "@io_k8s_sigs_controller_runtime//pkg/log/zap",
        "@io_k8s_sigs_controller_runtime//pkg/metrics/filters",
        "@io_k8s_sigs_controller_runtime//pkg/metrics/server",
        "@io_k8s_sigs_controller_runtime//pkg/webhook",
        "@io_k8s_sigs_gateway_api//apis/v1:apis",
    ],
)

go_binary(
    name = "cmd",
    embed = [":cmd_lib"],
    visibility = ["//visibility:public"],
)
