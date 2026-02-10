load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "copy",
    srcs = [
        "classify.go",
        "copy.go",
    ],
    importpath = "github.com/jomcgi/homelab/tools/hf2oci/pkg/copy",
    visibility = ["//visibility:public"],
    deps = [
        "//tools/hf2oci/pkg/hf",
        "//tools/hf2oci/pkg/oci",
        "@com_github_google_go_containerregistry//pkg/authn",
        "@com_github_google_go_containerregistry//pkg/name",
        "@com_github_google_go_containerregistry//pkg/v1:pkg",
        "@com_github_google_go_containerregistry//pkg/v1/remote",
    ],
)

go_test(
    name = "copy_test",
    srcs = [
        "classify_test.go",
        "copy_test.go",
    ],
    embed = [":copy"],
    deps = [
        "//tools/hf2oci/pkg/hf",
        "@com_github_google_go_containerregistry//pkg/name",
        "@com_github_google_go_containerregistry//pkg/registry",
        "@com_github_google_go_containerregistry//pkg/v1/remote",
        "@com_github_stretchr_testify//assert",
        "@com_github_stretchr_testify//require",
    ],
)
