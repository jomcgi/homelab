load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "types",
    srcs = [
        "alerts.go",
        "dashboard.go",
        "querybuilder.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/signoz_mcp_server/pkg/types",
    visibility = ["//visibility:public"],
)

go_test(
    name = "types_test",
    srcs = ["querybuilder_test.go"],
    embed = [":types"],
    deps = ["@com_github_stretchr_testify//require"],
)
