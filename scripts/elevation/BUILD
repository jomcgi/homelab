load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "elevation",
    srcs = [
        "__init__.py",
        "client.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//aiohttp"],
)
