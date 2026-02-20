load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py charts.bosun.backend.server //charts/bosun/backend:server_lib

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    data = glob(["fixtures/*.json"]),
    visibility = ["//:__subpackages__"],
    deps = [
        "//charts/bosun/backend:server_lib",
        "@pip//claude_agent_sdk",
        "@pip//pytest",
    ],
)

py_test(
    name = "api_endpoints_test",
    srcs = ["api_endpoints_test.py"],
    deps = [
        ":conftest",
        "@pip//pytest",
        "@pip//starlette",
    ],
)

py_test(
    name = "ws_artifacts_test",
    srcs = ["ws_artifacts_test.py"],
    deps = [
        ":conftest",
        "@pip//pytest",
        "@pip//starlette",
    ],
)

py_test(
    name = "ws_lifecycle_test",
    srcs = ["ws_lifecycle_test.py"],
    deps = [
        ":conftest",
        "@pip//claude_agent_sdk",
        "@pip//pytest",
        "@pip//starlette",
    ],
)

py_test(
    name = "ws_streaming_test",
    srcs = ["ws_streaming_test.py"],
    deps = [
        ":conftest",
        "@pip//pytest",
        "@pip//starlette",
    ],
)

py_test(
    name = "ws_tools_test",
    srcs = ["ws_tools_test.py"],
    deps = [
        ":conftest",
        "@pip//pytest",
        "@pip//starlette",
    ],
)
