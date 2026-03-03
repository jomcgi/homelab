load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

py_library(
    name = "delete-trip-points",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//httpx",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

semgrep_test(
    name = "main_semgrep_test",
    srcs = ["main.py"],
    rules = ["//semgrep_rules:python_rules"],
)
