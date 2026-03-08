load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "cmd",
    srcs = [
        "copy.go",
        "output.go",
        "resolve.go",
        "root.go",
    ],
    importpath = "github.com/jomcgi/homelab/bazel/tools/hf2oci/cmd/hf2oci/cmd",
    visibility = ["//visibility:public"],
    deps = [
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/copy:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/hf:go_default_library",
        "@com_github_spf13_cobra//:cobra",
    ],
)

go_test(
    name = "cmd_test",
    srcs = ["output_test.go"],
    embed = [":cmd"],
    deps = [
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/copy:go_default_library",
        "@com_github_stretchr_testify//assert",
        "@com_github_stretchr_testify//require",
    ],
)
