load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "n8n",
    srcs = [
        "client.go",
        "doc.go",
        "generated.go",
    ],
    importpath = "github.com/jomcgi/homelab/pkg/n8n",
    visibility = ["//visibility:public"],
    deps = [
        "@com_github_getkin_kin_openapi//openapi3",
        "@com_github_oapi_codegen_runtime//:runtime",
        "@com_github_oapi_codegen_runtime//types",
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel//codes",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)
