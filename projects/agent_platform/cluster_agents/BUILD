load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//bazel/tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cluster_agents_lib",
    srcs = [
        "collector_alerts.go",
        "escalator.go",
        "git_activity_gate.go",
        "github_client.go",
        "main.go",
        "model.go",
        "notification.go",
        "patrol.go",
        "pr_fix_agent.go",
        "readme_freshness_agent.go",
        "rules_agent.go",
        "runner.go",
        "test_coverage_agent.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/cluster_agents",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
    ],
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
        "git_activity_gate_test.go",
        "github_client_test.go",
        "main_test.go",
        "model_test.go",
        "notification_test.go",
        "patrol_test.go",
        "pr_fix_agent_test.go",
        "readme_freshness_agent_test.go",
        "rules_agent_test.go",
        "runner_test.go",
        "test_coverage_agent_test.go",
    ],
    embed = [":cluster_agents_lib"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_server_v2//server",
    ],
)

go_image(
    name = "image",
    binary = ":cluster-agents",
    repository = "ghcr.io/jomcgi/homelab/projects/agent_platform/cluster_agents",
)
