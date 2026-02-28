load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "tools",
    srcs = [
        "aggregate_helper.go",
        "handler.go",
        "logs_helper.go",
        "traces_helper.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/internal/handler/tools",
    visibility = ["//services/signoz_mcp_server:__subpackages__"],
    deps = [
        "//services/signoz_mcp_server/internal/client",
        "//services/signoz_mcp_server/pkg/dashboard",
        "//services/signoz_mcp_server/pkg/paginate",
        "//services/signoz_mcp_server/pkg/timeutil",
        "//services/signoz_mcp_server/pkg/types",
        "//services/signoz_mcp_server/pkg/util",
        "@com_github_mark3labs_mcp_go//mcp",
        "@com_github_mark3labs_mcp_go//server",
        "@org_uber_go_zap//:zap",
    ],
)
