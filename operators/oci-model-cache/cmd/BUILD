load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "cmd_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/operators/oci-model-cache/cmd",
    visibility = ["//visibility:private"],
    deps = [
        "//bazel/tools/hf2oci/pkg/copy",
        "//bazel/tools/hf2oci/pkg/hf",
        "//operators/oci-model-cache/api/v1alpha1:api",
        "//operators/oci-model-cache/internal/config",
        "//operators/oci-model-cache/internal/controller",
        "//operators/oci-model-cache/internal/statemachine",
        "//operators/oci-model-cache/internal/telemetry",
        "//operators/oci-model-cache/internal/webhook",
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
        "@io_k8s_sigs_controller_runtime//pkg/webhook/admission",
    ],
)

go_binary(
    name = "cmd",
    embed = [":cmd_lib"],
    visibility = ["//visibility:public"],
)
