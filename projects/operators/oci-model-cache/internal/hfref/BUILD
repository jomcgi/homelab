load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "hfref",
    srcs = ["parser.go"],
    importpath = "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/hfref",
    visibility = ["//projects/operators/oci-model-cache:__subpackages__"],
)

go_test(
    name = "hfref_test",
    srcs = ["parser_test.go"],
    embed = [":hfref"],
)
