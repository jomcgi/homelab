load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")

go_library(
    name = "cmd_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/projects/todo_app/cmd",
    visibility = ["//visibility:private"],
)

go_binary(
    name = "cmd",
    embed = [":cmd_lib"],
    visibility = ["//projects/todo_app/image:__pkg__"],
)

go_test(
    name = "cmd_test",
    srcs = [
        "git_commit_test.go",
        "main_test.go",
    ],
    embed = [":cmd_lib"],
)
