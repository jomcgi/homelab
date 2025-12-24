load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "cmd",
    srcs = [
        "generate.go",
        "root.go",
        "validate.go",
    ],
    importpath = "github.com/jomcgi/homelab/sextant/cmd/sextant/cmd",
    visibility = ["//visibility:public"],
    deps = [
        "//sextant/pkg/codegen",
        "//sextant/pkg/schema",
        "//sextant/pkg/xstate",
        "@com_github_spf13_cobra//:cobra",
    ],
)
