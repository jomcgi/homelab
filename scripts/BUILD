load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@multitool//:tools.bzl", MULTITOOL_TOOLS = "TOOLS")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

sh_binary(
    name = "signoz-mcp-wrapper",
    srcs = ["signoz-mcp-wrapper.sh"],
)

sh_binary(
    name = "generate-push-all",
    srcs = ["generate-push-all.sh"],
    visibility = ["//:__subpackages__"],
)

sh_binary(
    name = "generate-push-all-pages",
    srcs = ["generate-push-all-pages.sh"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "scripts",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

# Helm chart linting - standalone script for local use
# For CI, use individual chart lint targets in charts/*/BUILD
sh_binary(
    name = "test_charts",
    srcs = ["test-charts.sh"],
    visibility = ["//visibility:public"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
