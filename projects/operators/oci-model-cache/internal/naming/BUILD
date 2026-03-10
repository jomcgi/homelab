load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "naming",
    srcs = ["naming.go"],
    importpath = "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/naming",
    visibility = ["//projects/operators/oci-model-cache:__subpackages__"],
)

go_test(
    name = "naming_test",
    srcs = ["naming_test.go"],
    embed = [":naming"],
)
