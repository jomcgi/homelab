load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "cmd_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/charts/todo/cmd",
    visibility = ["//visibility:private"],
)

go_binary(
    name = "cmd",
    embed = [":cmd_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = ":cmd",
    visibility = ["//visibility:public"],
)
