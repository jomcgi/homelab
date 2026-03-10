load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")

go_library(
    name = "go_lib",
    srcs = ["solution.go"],
    importpath = "github.com/jomcgi/homelab/projects/advent_of_code/solutions/year2025/day03/go",
    visibility = ["//visibility:private"],
    deps = ["//projects/advent_of_code/pkg/aoc"],
)

go_binary(
    name = "go",
    data = ["//projects/advent_of_code/solutions/year2025/day03:input.txt"],
    embed = [":go_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "go_test",
    srcs = ["solution_test.go"],
    data = [
        "//projects/advent_of_code/solutions/year2025/day03:answers.json",  # keep
        "//projects/advent_of_code/solutions/year2025/day03:input.txt",  # keep
    ],
    embed = [":go_lib"],
    deps = ["//projects/advent_of_code/pkg/aoc"],
)
