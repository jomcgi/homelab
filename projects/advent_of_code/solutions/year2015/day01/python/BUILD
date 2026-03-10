load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "solution",
    srcs = ["solution.py"],
    main = "solution.py",
    visibility = ["//:__subpackages__"],
    deps = ["//projects/advent_of_code/python/aoc"],
)

py_library(
    name = "python",
    srcs = [
        "__init__.py",
        "solution.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["//projects/advent_of_code/python/aoc"],
)

py_test(
    name = "solution_test",
    srcs = ["solution_test.py"],
    data = [
        "//projects/advent_of_code/solutions/year2015/day01:answers.json",  # keep
        "//projects/advent_of_code/solutions/year2015/day01:input.txt",  # keep
    ],
    deps = [
        ":python",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "solution_test_semgrep_test",
    srcs = ["solution_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_target_test(
    name = "solution_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":solution",
)
