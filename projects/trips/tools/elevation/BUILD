load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

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
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "client_semgrep_test",
    srcs = ["client.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "elevation_test",
    srcs = ["elevation_test.py"],
    imports = ["."],
    deps = [
        ":elevation",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "elevation_test_semgrep_test",
    srcs = ["elevation_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
