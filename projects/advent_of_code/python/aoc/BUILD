load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "aoc",
    srcs = [
        "__init__.py",
        "algo.py",
        "grid.py",
        "parse.py",
    ],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "algo_test",
    srcs = ["algo_test.py"],
    deps = [
        ":aoc",
        "@pip//pytest",
    ],
)

py_test(
    name = "grid_test",
    srcs = ["grid_test.py"],
    deps = [
        ":aoc",
        "@pip//pytest",
    ],
)

py_test(
    name = "parse_test",
    srcs = ["parse_test.py"],
    deps = [
        ":aoc",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "algo_semgrep_test",
    srcs = ["algo.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "grid_semgrep_test",
    srcs = ["grid.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "parse_semgrep_test",
    srcs = ["parse.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
