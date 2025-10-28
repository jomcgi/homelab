load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "config",
    srcs = [
        "__init__.py",
        "config.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pydantic_settings"],
)
