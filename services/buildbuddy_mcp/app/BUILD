load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)
