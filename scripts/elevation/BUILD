load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_library(
    name = "elevation",
    srcs = [
        "__init__.py",
        "client.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//aiohttp"],
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
