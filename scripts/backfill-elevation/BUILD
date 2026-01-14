load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//scripts/elevation",
        "@pip//nats_py",
        "@pip//rich",
        "@pip//typer",
    ],
)

py_library(
    name = "backfill-elevation",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//scripts/elevation",
        "@pip//nats_py",
        "@pip//rich",
        "@pip//typer",
    ],
)
