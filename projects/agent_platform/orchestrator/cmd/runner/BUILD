load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")

go_library(
    name = "runner_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/orchestrator/cmd/runner",
    visibility = ["//visibility:private"],
)

go_binary(
    name = "runner",
    embed = [":runner_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "runner_test",
    srcs = [
        "main_test.go",
        "runner_session_test.go",
    ],
    embed = [":runner_lib"],
)
