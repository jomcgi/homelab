# gazelle:semgrep disabled
# gazelle:exclude golang
# gazelle:exclude python
# gazelle:exclude typescript
# gazelle:exclude yaml

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
    name = "yaml_rules",
    srcs = glob(
        ["yaml/*.yaml"],
        allow_empty = True,
    ),
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
    name = "typescript_rules",
    srcs = glob(
        ["typescript/*.yaml"],
        allow_empty = True,
    ),
)

filegroup(
    name = "javascript_rules",
    srcs = [
        ":typescript_rules",
        "@semgrep_pro_rules_javascript//:rules",
    ],
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
    name = "generic_rules",
    srcs = glob(
        ["generic/*.yaml"],
        allow_empty = True,
    ),
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
    name = "kubernetes_rules_test",
    srcs = ["//bazel/semgrep/tests:kubernetes_yaml_fixtures"],
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":kubernetes_rules"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "yaml_rules_test",
    srcs = ["//bazel/semgrep/tests:yaml_fixtures"],
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":yaml_rules"],
    tags = ["semgrep"],
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

semgrep_test(
    name = "typescript_rules_test",
    srcs = ["//bazel/semgrep/tests:typescript_fixtures"],
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":typescript_rules"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "generic_rules_test",
    srcs = ["//bazel/semgrep/tests:no_stale_repo_paths_fixtures"],
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":generic_rules"],
    tags = ["semgrep"],
)

# stale-copyright-year uses languages: [generic] so its fixture is a YAML file.
# This test wires the rule to its annotation fixture independently of
# golang_rules_test (which only scans *.go sources).
filegroup(
    name = "stale_copyright_year_rule",
    srcs = ["golang/stale-copyright-year.yaml"],
)

semgrep_test(
    name = "stale_copyright_year_test",
    srcs = ["//bazel/semgrep/tests:stale_copyright_year_fixtures"],
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":stale_copyright_year_rule"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "shell_rules_test",
    srcs = glob(["shell/*.bash"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":shell_rules"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "bazel_rules_test",
    srcs = glob(["bazel/*.build"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":bazel_rules"],
    tags = ["semgrep"],
)

semgrep_test(
    name = "dockerfile_rules_test",
    srcs = glob(["dockerfile/*.dockerfile"]),
    env = {"SEMGREP_TEST_MODE": "1"},
    rules = [":dockerfile_rules"],
    tags = ["semgrep"],
)
