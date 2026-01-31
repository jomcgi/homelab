load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//defusedxml",
        "@pip//nats_py",
        "@pip//typer",
    ],
)

py_library(
    name = "publish-gap-route",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//defusedxml",
        "@pip//nats_py",
        "@pip//typer",
    ],
)
