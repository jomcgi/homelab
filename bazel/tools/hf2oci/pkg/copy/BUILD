load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "copy",
    srcs = [
        "classify.go",
        "copy.go",
        "errors.go",
        "resolve.go",
    ],
    importpath = "github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/copy",
    visibility = ["//visibility:public"],
    deps = [
        "@com_github_google_go_containerregistry//pkg/authn",
        "@com_github_google_go_containerregistry//pkg/name",
        "@com_github_google_go_containerregistry//pkg/v1:pkg",
        "@com_github_google_go_containerregistry//pkg/v1/remote",
        "@com_github_google_go_containerregistry//pkg/v1/remote/transport",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/gguf:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/hf:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/oci:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/ociref:go_default_library",
        "@org_golang_x_sync//errgroup",
    ],
)

go_test(
    name = "copy_test",
    srcs = [
        "classify_test.go",
        "copy_test.go",
        "resolve_test.go",
    ],
    embed = [":copy"],
    deps = [
        "@com_github_google_go_containerregistry//pkg/name",
        "@com_github_google_go_containerregistry//pkg/registry",
        "@com_github_google_go_containerregistry//pkg/v1/remote",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/gguf:go_default_library",
        "@com_github_jomcgi_homelab//tools/hf2oci/pkg/hf:go_default_library",
        "@com_github_stretchr_testify//assert",
        "@com_github_stretchr_testify//require",
    ],
)
