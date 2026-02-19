load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "server",
    srcs = ["server.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//claude_agent_sdk",
        "@pip//fastapi",
        "@pip//google_genai",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "backend",
    srcs = [
        "__init__.py",
        "server.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//claude_agent_sdk",
        "@pip//fastapi",
        "@pip//google_genai",
        "@pip//uvicorn",
    ],
)

py_test(
    name = "test_tts_on_result",
    srcs = ["test_tts_on_result.py"],
    deps = [
        ":backend",
        "@pip//claude_agent_sdk",
        "@pip//pytest",
        "@pip//starlette",
    ],
)
