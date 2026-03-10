load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py buildbuddy_mcp.app.main //projects/agent-platform/buildbuddy_mcp/app:app

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    imports = ["../.."],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    imports = ["../.."],
    deps = [
        ":conftest",
        "@pip//pytest",
    ],
)

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    imports = ["../.."],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pytest_asyncio"],
)

py_test(
    name = "composite_test",
    srcs = ["composite_test.py"],
    imports = ["../.."],
    deps = [
        ":conftest",
        "@pip//pytest",
    ],
)

py_test(
    name = "proto_conformance_test",
    srcs = ["proto_conformance_test.py"],
    imports = ["../.."],
    local = True,
    tags = ["external"],
    deps = [
        ":conftest",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "composite_test_semgrep_test",
    srcs = ["composite_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "proto_conformance_test_semgrep_test",
    srcs = ["proto_conformance_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
