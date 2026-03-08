load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cluster-agents_lib",
    srcs = [
        "collector_argocd.go",
        "collector_k8s.go",
        "escalator.go",
        "llm.go",
        "main.go",
        "model.go",
        "patrol.go",
        "runner.go",
        "store.go",
        "store_nats.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/cluster-agents",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
    ],
)

go_binary(
    name = "cluster-agents",
    embed = [":cluster-agents_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "cluster-agents_unit_test",
    srcs = [
        "collector_argocd_test.go",
        "collector_k8s_test.go",
        "escalator_test.go",
        "llm_test.go",
        "patrol_test.go",
        "runner_test.go",
    ],
    embed = [":cluster-agents_lib"],
    deps = [
        "@io_k8s_client_go//kubernetes/fake",
    ],
)

go_test(
    name = "cluster-agents_test",
    srcs = [
        "collector_argocd_test.go",
        "collector_k8s_test.go",
        "escalator_test.go",
        "llm_test.go",
        "patrol_test.go",
        "runner_test.go",
        "store_test.go",
    ],
    embed = [":cluster-agents_lib"],
    tags = ["manual"],
    deps = [
        "@io_k8s_client_go//kubernetes/fake",
    ],
)

go_image(
    name = "image",
    binary = ":cluster-agents",
    repository = "ghcr.io/jomcgi/homelab/services/cluster-agents",
)
