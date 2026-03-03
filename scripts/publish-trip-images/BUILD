load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_library(
    name = "publish-trip-images",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//botocore",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//rich",
        "@pip//typer",
    ],
)

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//botocore",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//rich",
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
