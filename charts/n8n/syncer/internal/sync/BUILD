load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "sync",
    srcs = ["syncer.go"],
    importpath = "github.com/jomcgi/homelab/charts/n8n/syncer/internal/sync",
    visibility = ["//charts/n8n/syncer:__subpackages__"],
    deps = [
        "//pkg/n8n",
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel//codes",
        "@io_opentelemetry_go_otel_metric//:metric",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)
