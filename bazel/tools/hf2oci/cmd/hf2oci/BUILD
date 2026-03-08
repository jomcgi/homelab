load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "hf2oci_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/bazel/tools/hf2oci/cmd/hf2oci",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_jomcgi_homelab//tools/hf2oci/cmd/hf2oci/cmd:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/copy:go_default_library",
    ],
)

go_binary(
    name = "hf2oci",
    embed = [":hf2oci_lib"],
    visibility = ["//visibility:public"],
)
