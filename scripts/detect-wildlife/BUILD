load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_library(
    name = "detect-wildlife",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//open_gopro",
        "@pip//typer",
    ],
)

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//open_gopro",
        "@pip//typer",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "main_semgrep_test",
    srcs = ["main.py"],
    rules = ["//semgrep_rules:python_rules"],
)
