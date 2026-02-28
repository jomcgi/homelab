load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "logger",
    srcs = ["logger.go"],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/internal/logger",
    visibility = ["//services/signoz_mcp_server:__subpackages__"],
    deps = ["@org_uber_go_zap//:zap"],
)
