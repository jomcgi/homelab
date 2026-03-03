load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "solution",
    srcs = ["solution.py"],
    visibility = ["//:__subpackages__"],
    deps = ["//advent_of_code/python/aoc"],
)

py_library(
    name = "python",
    srcs = [
        "__init__.py",
        "solution.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["//advent_of_code/python/aoc"],
)

py_test(
    name = "solution_test",
    srcs = ["solution_test.py"],
    data = [
        "//advent_of_code/solutions/year2015/day03:answers.json",  # keep
        "//advent_of_code/solutions/year2015/day03:input.txt",  # keep
    ],
    deps = [
        ":python",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
