load("@rules_go//go:def.bzl", "go_binary", "go_library")

go_library(
    name = "aoc_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/advent_of_code/cmd/aoc",
    visibility = ["//visibility:private"],
    deps = [
        "//advent_of_code/pkg/aoc",
        "//advent_of_code/pkg/cookies",
        "@com_github_spf13_cobra//:cobra",
    ],
)

go_binary(
    name = "aoc",
    embed = [":aoc_lib"],
    visibility = ["//visibility:public"],
)
