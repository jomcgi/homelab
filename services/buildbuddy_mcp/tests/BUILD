load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py services.buildbuddy_mcp.app.main //services/buildbuddy_mcp/app:app

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
        "//services/buildbuddy_mcp/app",
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

py_test(
    name = "composite_test",
    srcs = ["composite_test.py"],
    deps = [
        ":conftest",
        "//services/buildbuddy_mcp/app",
        "@pip//pytest",
    ],
)

py_test(
    name = "proto_conformance_test",
    srcs = ["proto_conformance_test.py"],
    deps = [
        ":conftest",
        "//services/buildbuddy_mcp/app",
        "@pip//httpx",
        "@pip//pytest",
    ],
)
