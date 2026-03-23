# gazelle:semgrep_exclude_rules no-mcp-run-http
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
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
        "@pip//httpx",
        "@pip//pydantic_settings",
        "@pip//starlette",
        "@pip//uvicorn",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    exclude_rules = ["no-mcp-run-http"],
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    exclude_rules = ["no-mcp-run-http"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
