load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "statemachine",
    srcs = [
        "model_cache_calculator.go",
        "model_cache_metrics.go",
        "model_cache_observability.go",
        "model_cache_phases.go",
        "model_cache_status.go",
        "model_cache_transitions.go",
        "model_cache_types.go",
        "model_cache_visit.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine",
    visibility = ["//projects/operators/oci-model-cache:__subpackages__"],
    deps = [
        "//projects/operators/oci-model-cache/api/v1alpha1:api",
        "@com_github_go_logr_logr//:logr",
        "@com_github_prometheus_client_golang//prometheus",
        "@io_k8s_sigs_controller_runtime//:controller-runtime",
        "@io_k8s_sigs_controller_runtime//pkg/client",
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)

go_test(
    name = "statemachine_test",
    srcs = ["statemachine_test.go"],
    embed = [":statemachine"],
    deps = [
        "//projects/operators/oci-model-cache/api/v1alpha1:api",
        "@com_github_go_logr_logr//testr",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
    ],
)
