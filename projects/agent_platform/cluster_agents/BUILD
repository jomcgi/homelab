load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//bazel/tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cluster_agents_lib",
    srcs = [
        "collector_alerts.go",
        "escalator.go",
        "main.go",
        "model.go",
        "patrol.go",
        "runner.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/cluster_agents",
    visibility = ["//visibility:private"],
)

go_binary(
    name = "cluster-agents",
    embed = [":cluster_agents_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "cluster_agents_test",
    srcs = [
        "collector_alerts_test.go",
        "escalator_test.go",
        "patrol_test.go",
        "runner_test.go",
    ],
    embed = [":cluster_agents_lib"],
)

go_image(
    name = "image",
    binary = ":cluster-agents",
)
