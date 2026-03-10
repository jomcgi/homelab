load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "statemachine",
    srcs = [
        "cloudflare_tunnel_calculator.go",
        "cloudflare_tunnel_metrics.go",
        "cloudflare_tunnel_observability.go",
        "cloudflare_tunnel_phases.go",
        "cloudflare_tunnel_status.go",
        "cloudflare_tunnel_transitions.go",
        "cloudflare_tunnel_types.go",
        "cloudflare_tunnel_visit.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/statemachine",
    visibility = ["//projects/operators/cloudflare:__subpackages__"],
    deps = [
        "//projects/operators/cloudflare/api/v1:api",
        "@com_github_go_logr_logr//:logr",
        "@com_github_prometheus_client_golang//prometheus",
        "@io_k8s_sigs_controller_runtime//:controller-runtime",
        "@io_k8s_sigs_controller_runtime//pkg/client",
        "@io_opentelemetry_go_otel//:otel",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel_trace//:trace",
    ],
)
