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
        "//services/buildbuddy_mcp/app",
        "@pip//pytest",
    ],
)
