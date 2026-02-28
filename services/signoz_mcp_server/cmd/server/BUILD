load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "server_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/cmd/server",
    visibility = ["//visibility:private"],
    deps = [
        "//services/signoz_mcp_server/internal/client",
        "//services/signoz_mcp_server/internal/config",
        "//services/signoz_mcp_server/internal/handler/tools",
        "//services/signoz_mcp_server/internal/logger",
        "//services/signoz_mcp_server/internal/mcp-server",
        "//services/signoz_mcp_server/pkg/dashboard",
        "@org_uber_go_zap//:zap",
    ],
)

go_binary(
    name = "server",
    embed = [":server_lib"],
    visibility = ["//visibility:public"],
)
