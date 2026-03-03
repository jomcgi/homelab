load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_venv_binary(
    name = "main",
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "composite.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "composite_semgrep_test",
    srcs = ["composite.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "main_semgrep_test",
    srcs = ["main.py"],
    rules = ["//semgrep_rules:python_rules"],
)
