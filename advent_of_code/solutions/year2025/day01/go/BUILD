load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")

go_library(
    name = "go_lib",
    srcs = ["solution.go"],
    importpath = "github.com/jomcgi/homelab/advent_of_code/solutions/year2025/day01/go",
    visibility = ["//visibility:private"],
    deps = ["//advent_of_code/pkg/aoc"],
)

go_binary(
    name = "go",
    embed = [":go_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "go_test",
    srcs = ["solution_test.go"],
    data = [
        "//advent_of_code/solutions/year2025/day01:answers.json",  # keep
        "//advent_of_code/solutions/year2025/day01:input.txt",  # keep
    ],
    embed = [":go_lib"],
    deps = ["//advent_of_code/pkg/aoc"],
)
