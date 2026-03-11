load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "agent_orchestrator_mcp",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "image",
    binary = "//projects/agent_platform/orchestrator/mcp/app:main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
