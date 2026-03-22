load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "cookies",
    srcs = ["cookies.go"],
    importpath = "github.com/jomcgi/homelab/projects/advent_of_code/pkg/cookies",
    visibility = ["//visibility:public"],
)

go_test(
    name = "cookies_test",
    srcs = ["cookies_test.go"],
    embed = [":cookies"],
)
