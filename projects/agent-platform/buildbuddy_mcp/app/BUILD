load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")

# gazelle:resolve py buildbuddy_mcp.app.composite //projects/agent-platform/buildbuddy_mcp/app:app
# gazelle:resolve py buildbuddy_mcp.app //projects/agent-platform/buildbuddy_mcp/app:app
# gazelle:resolve py buildbuddy_mcp //projects/agent-platform/buildbuddy_mcp:buildbuddy_mcp

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    imports = ["../.."],
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
        "composite.py",
        "main.py",
    ],
    imports = ["../.."],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "composite_semgrep_test",
    srcs = ["composite.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
