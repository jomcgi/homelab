load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

py_library(
    name = "todo_mcp",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
    deps = ["//projects/todo_app"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
