load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "hf2oci_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/tools/hf2oci/cmd/hf2oci",
    visibility = ["//visibility:private"],
    deps = ["//tools/hf2oci/cmd/hf2oci/cmd"],
)

go_binary(
    name = "hf2oci",
    embed = [":hf2oci_lib"],
    visibility = ["//visibility:public"],
)
