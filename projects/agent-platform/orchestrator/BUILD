load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//bazel/tools/oci:go_image.bzl", "go_image")

# gazelle:map_kind go_test go_test @rules_go//go:def.bzl

go_library(
    name = "agent-orchestrator_lib",
    srcs = [
        "api.go",
        "consumer.go",
        "main.go",
        "model.go",
        "reconcile.go",
        "sandbox.go",
        "store.go",
        "ui.go",
        "watchdog.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/agent-platform/orchestrator",
    visibility = ["//visibility:private"],
    deps = [
        "//projects/agent-platform/orchestrator/ui",
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@com_github_oklog_ulid_v2//:ulid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/errors",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
    ],
)

go_binary(
    name = "agent-orchestrator",
    embed = [":agent-orchestrator_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "agent-orchestrator_unit_test",
    srcs = [
        "api_test.go",
        "consumer_test.go",
        "reconcile_test.go",
        "sandbox_test.go",
        "watchdog_test.go",
    ],
    embed = [":agent-orchestrator_lib"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
    ],
)

go_test(
    name = "agent-orchestrator_test",
    srcs = [
        "api_test.go",
        "consumer_test.go",
        "reconcile_test.go",
        "sandbox_test.go",
        "store_test.go",
        "watchdog_test.go",
    ],
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

# NOTE: Do not add an orchestrator_test target here — gazelle incorrectly
# generates one referencing :orchestrator_lib (which doesn't exist).
# The correct test targets are agent-orchestrator_unit_test and
# agent-orchestrator_test above.
