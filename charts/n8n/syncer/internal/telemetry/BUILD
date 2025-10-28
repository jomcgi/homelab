load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "telemetry",
    srcs = ["telemetry.go"],
    importpath = "github.com/jomcgi/homelab/charts/n8n/syncer/internal/telemetry",
    visibility = ["//charts/n8n/syncer:__subpackages__"],
    deps = [
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//semconv/v1.24.0:v1_24_0",
        "@io_opentelemetry_go_otel_exporters_otlp_otlptrace//:otlptrace",
        "@io_opentelemetry_go_otel_exporters_otlp_otlptrace_otlptracegrpc//:otlptracegrpc",
        "@io_opentelemetry_go_otel_sdk//resource",
        "@io_opentelemetry_go_otel_sdk//trace",
    ],
)
