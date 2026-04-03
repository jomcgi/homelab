load("@rules_go//go:def.bzl", "go_library", "go_test")

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

go_test(
    name = "statemachine_test",
    srcs = [
        "cloudflare_tunnel_calculator_status_transitions_visit_test.go",
        "cloudflare_tunnel_comprehensive_test.go",
        "cloudflare_tunnel_coverage_gaps_test.go",
        "cloudflare_tunnel_extra_test.go",
        "cloudflare_tunnel_gaps_test.go",
        "cloudflare_tunnel_metrics_test.go",
        "cloudflare_tunnel_observability_test.go",
        "cloudflare_tunnel_statemachine_test.go",
    ],
    embed = [":statemachine"],
    deps = [
        "//projects/operators/cloudflare/api/v1:api",
        "@com_github_go_logr_logr//:logr",
        "@com_github_onsi_ginkgo_v2//:ginkgo",
        "@com_github_onsi_gomega//:gomega",
        "@com_github_prometheus_client_golang//prometheus/testutil",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_sigs_controller_runtime//pkg/client",
        "@io_opentelemetry_go_otel//:otel",
    ],
)
