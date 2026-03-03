load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_library(
    name = "day03",
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
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
