load("@rules_go//go:def.bzl", "go_library", "go_test")

go_library(
    name = "gguf",
    srcs = [
        "parse.go",
        "size.go",
        "split.go",
        "types.go",
        "write.go",
    ],
    importpath = "github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/gguf",
    visibility = ["//visibility:public"],
)

go_test(
    name = "gguf_test",
    srcs = [
        "parse_test.go",
        "size_test.go",
        "split_test.go",
        "write_test.go",
    ],
    embed = [":gguf"],
)
