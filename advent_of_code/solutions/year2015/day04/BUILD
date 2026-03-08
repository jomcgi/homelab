load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

py_library(
    name = "day04",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

exports_files(
    [
        "input.txt",
        "answers.json",
    ],
    visibility = ["//:__subpackages__"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
