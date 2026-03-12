load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "aoc",
    srcs = [
        "algo.go",
        "client.go",
        "grid.go",
        "parse.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc",
    visibility = ["//visibility:public"],
)

go_test(
    name = "aoc_test",
    srcs = [
        "algo_test.go",
        "client_test.go",
        "grid_test.go",
        "parse_test.go",
    ],
    embed = [":aoc"],
)
