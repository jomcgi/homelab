# gazelle:semgrep disabled
# gazelle:exclude python

load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "shell_rules",
    srcs = glob(["shell/*.yaml"]),
)

filegroup(
    name = "bazel_rules",
    srcs = glob(["bazel/*.yaml"]),
)

filegroup(
    name = "dockerfile_rules",
    srcs = glob(["dockerfile/*.yaml"]),
)

filegroup(
    name = "kubernetes_rules",
    srcs = glob(
        ["kubernetes/*.yaml"],
        allow_empty = True,
    ) + ["@semgrep_pro_rules_kubernetes//:rules"],
)

filegroup(
    name = "python_rules",
    srcs = glob(["python/*.yaml"]) + ["@semgrep_pro_rules_python//:rules"],
)

filegroup(
    name = "golang_rules",
    srcs = glob(
        ["golang/*.yaml"],
        allow_empty = True,
    ) + ["@semgrep_pro_rules_golang//:rules"],
)

filegroup(
    name = "javascript_rules",
    srcs = ["@semgrep_pro_rules_javascript//:rules"],
)

filegroup(
    name = "sca_golang_rules",
    srcs = ["@semgrep_sca_rules_golang//:rules"],
)

filegroup(
    name = "sca_python_rules",
    srcs = ["@semgrep_sca_rules_python//:rules"],
)

filegroup(
    name = "sca_javascript_rules",
    srcs = ["@semgrep_sca_rules_javascript//:rules"],
)

filegroup(
    name = "sca_rules",
    srcs = [
        ":sca_golang_rules",
        ":sca_javascript_rules",
        ":sca_python_rules",
    ],
)

filegroup(
    name = "all_rules",
    srcs = glob(["**/*.yaml"]) + [
        "@semgrep_pro_rules_golang//:rules",
        "@semgrep_pro_rules_javascript//:rules",
        "@semgrep_pro_rules_kubernetes//:rules",
        "@semgrep_pro_rules_python//:rules",
    ],
)

semgrep_test(
    name = "golang_rules_test",
    srcs = glob(["golang/*.go"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":golang_rules"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "python_rules_test",
    srcs = glob(["python/*.py"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":python_rules"],
    tags = ["semgrep"],
)
