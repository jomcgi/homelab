load("@rules_go//go:def.bzl", "go_test")

go_test(
    name = "e2e_test",
    srcs = [
        "e2e_suite_test.go",
        "e2e_test.go",
    ],
    deps = ["//operators/cloudflare/test/utils"],
)
