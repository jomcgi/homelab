load("@rules_go//go:def.bzl", "go_library")

go_library(
    name = "cmd",
    srcs = [
        "copy.go",
        "output.go",
        "resolve.go",
        "root.go",
    ],
    importpath = "github.com/jomcgi/homelab/tools/hf2oci/cmd/hf2oci/cmd",
    visibility = ["//visibility:public"],
    deps = [
        "//tools/hf2oci/pkg/copy",
        "//tools/hf2oci/pkg/hf",
        "@com_github_spf13_cobra//:cobra",
    ],
)
