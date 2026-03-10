load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "cloudflare",
    srcs = [
        "access.go",
        "client.go",
        "dns.go",
        "routes.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare",
    visibility = ["//projects/operators/cloudflare:__subpackages__"],
    deps = [
        "//projects/operators/cloudflare/internal/telemetry",
        "@com_github_cloudflare_cloudflare_go//:cloudflare-go",
        "@com_github_sony_gobreaker//:gobreaker",
        "@io_opentelemetry_go_otel//attribute",
        "@io_opentelemetry_go_otel//codes",
        "@io_opentelemetry_go_otel_trace//:trace",
        "@org_golang_x_time//rate",
    ],
)

go_test(
    name = "cloudflare_test",
    srcs = ["client_test.go"],
    embed = [":cloudflare"],
    deps = [
        "@com_github_cloudflare_cloudflare_go//:cloudflare-go",
        "@com_github_onsi_ginkgo_v2//:ginkgo",
        "@com_github_onsi_gomega//:gomega",
    ],
)
