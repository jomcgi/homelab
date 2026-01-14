load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

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
