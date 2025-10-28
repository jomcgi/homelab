load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "models",
    srcs = [
        "__init__.py",
        "generated.py",
        "obsidian.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pydantic"],
)
