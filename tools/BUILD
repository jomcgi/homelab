load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

exports_files(
    ["__init__.py"],
    visibility = ["//bazel/tools/image:__pkg__"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_library(
    name = "tools",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)
