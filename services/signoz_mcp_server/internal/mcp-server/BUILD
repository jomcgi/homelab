load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "mcp-server",
    srcs = ["server.go"],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/internal/mcp-server",
    visibility = ["//services/signoz_mcp_server:__subpackages__"],
    deps = [
        "//services/signoz_mcp_server/internal/config",
        "//services/signoz_mcp_server/internal/handler/tools",
        "//services/signoz_mcp_server/pkg/util",
        "@com_github_mark3labs_mcp_go//server",
        "@org_uber_go_zap//:zap",
    ],
)
