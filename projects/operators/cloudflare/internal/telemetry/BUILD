load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "telemetry",
    srcs = ["tracing.go"],
    importpath = "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry",
    visibility = ["//projects/operators/cloudflare:__subpackages__"],
    deps = [
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel_exporters_otlp_otlptrace_otlptracegrpc//:otlptracegrpc",
        "@io_opentelemetry_go_otel_sdk//resource",
        "@io_opentelemetry_go_otel_sdk//trace",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)

go_test(
    name = "telemetry_test",
    srcs = ["tracing_test.go"],
    embed = [":telemetry"],
    deps = [
        "@com_github_onsi_ginkgo_v2//:ginkgo",
        "@com_github_onsi_gomega//:gomega",
        "@io_opentelemetry_go_otel//:otel",
    ],
)
