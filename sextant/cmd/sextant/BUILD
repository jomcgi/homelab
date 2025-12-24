load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "sextant_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/sextant/cmd/sextant",
    visibility = ["//visibility:private"],
    deps = ["//sextant/cmd/sextant/cmd"],
)

go_binary(
    name = "sextant",
    embed = [":sextant_lib"],
    visibility = ["//visibility:public"],
)
