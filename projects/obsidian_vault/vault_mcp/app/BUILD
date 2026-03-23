# gazelle:semgrep_exclude_rules mcp-shell-injection-taint
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")

exports_files(
    ["main.py"],
    visibility = ["//projects/obsidian_vault/image:__pkg__"],
)

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//pydantic_settings",
        "@pip//starlette",
        "@pip//uvicorn",
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
        "@pip//pydantic_settings",
        "@pip//starlette",
        "@pip//uvicorn",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    exclude_rules = ["mcp-shell-injection-taint"],
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    exclude_rules = ["mcp-shell-injection-taint"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
