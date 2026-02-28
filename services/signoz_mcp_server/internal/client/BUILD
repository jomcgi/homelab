load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "client",
    srcs = ["client.go"],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/internal/client",
    visibility = ["//services/signoz_mcp_server:__subpackages__"],
    deps = [
        "//services/signoz_mcp_server/pkg/types",
        "@org_uber_go_zap//:zap",
    ],
)

go_test(
    name = "client_test",
    srcs = ["client_test.go"],
    embed = [":client"],
    deps = [
        "//services/signoz_mcp_server/pkg/types",
        "@com_github_stretchr_testify//assert",
        "@com_github_stretchr_testify//require",
        "@org_uber_go_zap//:zap",
    ],
)
