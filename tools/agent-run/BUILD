load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "agent-run_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/tools/agent-run",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_spf13_cobra//:cobra",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_apimachinery//pkg/apis/meta/v1/unstructured",
        "@io_k8s_apimachinery//pkg/runtime/schema",
        "@io_k8s_apimachinery//pkg/watch",
        "@io_k8s_client_go//dynamic",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//tools/clientcmd",
    ],
)

go_binary(
    name = "agent-run",
    embed = [":agent-run_lib"],
    visibility = ["//visibility:public"],
)
