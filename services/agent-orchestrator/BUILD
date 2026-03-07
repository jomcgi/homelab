load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "agent-orchestrator_lib",
    srcs = [
        "api.go",
        "consumer.go",
        "main.go",
        "model.go",
        "sandbox.go",
        "store.go",
        "watchdog.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/agent-orchestrator",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@com_github_oklog_ulid_v2//:ulid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_client_go//dynamic",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//kubernetes/scheme",
        "@io_k8s_client_go//rest",
        "@io_k8s_client_go//tools/remotecommand",
        "@io_k8s_client_go//util/exec",
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
        "watchdog_test.go",
    ],
    embed = [":agent-orchestrator_lib"],
)

go_test(
    name = "agent-orchestrator_test",
    srcs = [
        "api_test.go",
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
