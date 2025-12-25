load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

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
