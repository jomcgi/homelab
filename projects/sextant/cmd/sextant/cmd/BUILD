load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "cmd",
    srcs = [
        "generate.go",
        "root.go",
        "validate.go",
    ],
    importpath = "github.com/jomcgi/homelab/projects/sextant/cmd/sextant/cmd",
    visibility = ["//visibility:public"],
    deps = [
        "//projects/sextant/pkg/codegen",
        "//projects/sextant/pkg/schema",
        "//projects/sextant/pkg/xstate",
        "@com_github_spf13_cobra//:cobra",
    ],
)

go_test(
    name = "cmd_test",
    srcs = ["cmd_test.go"],
    embed = [":cmd"],
    deps = [
        "@com_github_spf13_cobra//:cobra",
    ],
)
