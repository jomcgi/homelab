load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "cloudflare",
    srcs = ["client.go"],
    importpath = "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare",
    visibility = ["//operators/cloudflare:__subpackages__"],
    deps = ["//operators/cloudflare/internal/telemetry"],
)

go_test(
    name = "cloudflare_test",
    srcs = ["client_test.go"],
    embed = [":cloudflare"],
)
