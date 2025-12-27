load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_library(
    name = "publish-trip-images",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//typer",
    ],
)

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//nats_py",
        "@pip//pillow",
        "@pip//typer",
    ],
)
