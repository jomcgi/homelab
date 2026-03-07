load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "agent-orchestrator_lib",
    srcs = [
        "api.go",
        "main.go",
        "model.go",
        "store.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/agent-orchestrator",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//jetstream",
        "@com_github_oklog_ulid_v2//:ulid",
    ],
)

go_binary(
    name = "agent-orchestrator",
    embed = [":agent-orchestrator_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "agent-orchestrator_unit_test",
    srcs = ["api_test.go"],
    embed = [":agent-orchestrator_lib"],
)

go_test(
    name = "agent-orchestrator_test",
    srcs = ["store_test.go"],
    embed = [":agent-orchestrator_lib"],
    tags = ["manual"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
    ],
)

go_image(
    name = "image",
    binary = ":agent-orchestrator",
    repository = "ghcr.io/jomcgi/homelab/services/agent-orchestrator",
)
