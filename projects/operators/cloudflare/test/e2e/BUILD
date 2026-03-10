load("@rules_go//go:def.bzl", "go_test")

go_test(
    name = "e2e_test",
    srcs = [
        "e2e_suite_test.go",
        "e2e_test.go",
    ],
    tags = ["manual"],  # Requires Kind cluster and make-based docker build - needs Bazel migration
    deps = [
        "//projects/operators/cloudflare/test/utils",
        "@com_github_onsi_ginkgo_v2//:ginkgo",
        "@com_github_onsi_gomega//:gomega",
    ],
)
