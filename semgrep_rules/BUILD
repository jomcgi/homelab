# gazelle:semgrep disabled
# gazelle:exclude python

load("//rules_semgrep:defs.bzl", "semgrep_test")

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
    ),
)

filegroup(
    name = "python_rules",
    srcs = glob(["python/*.yaml"]),
)

filegroup(
    name = "all_rules",
    srcs = glob(["**/*.yaml"]),
)

semgrep_test(
    name = "python_rules_test",
    srcs = glob(["python/*.py"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":python_rules"],
    tags = ["semgrep"],
)
