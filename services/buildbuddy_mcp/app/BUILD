load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")

py_venv_binary(
    name = "main",
    main = "main.py",
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
