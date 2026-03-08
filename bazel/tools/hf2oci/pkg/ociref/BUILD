load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "ociref",
    srcs = ["ociref.go"],
    importpath = "github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/ociref",
    visibility = ["//visibility:public"],
    deps = ["@com_github_jomcgi_homelab//tools/hf2oci/pkg/hf:go_default_library"],
)

go_test(
    name = "ociref_test",
    srcs = ["ociref_test.go"],
    embed = [":ociref"],
    deps = [
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/hf:go_default_library",
        "@com_github_stretchr_testify//assert",
    ],
)
