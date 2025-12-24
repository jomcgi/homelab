load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "xstate",
    srcs = [
        "convert.go",
        "types.go",
    ],
    importpath = "github.com/jomcgi/homelab/sextant/pkg/xstate",
    visibility = ["//visibility:public"],
    deps = ["//sextant/pkg/schema"],
)
