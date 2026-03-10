load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py projects.agent_platform.orchestrator.mcp.app.main //projects/agent-platform/orchestrator/mcp/app:app

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/orchestrator/mcp/app",
        "@pip//pytest",
    ],
)

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pytest_asyncio"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
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
