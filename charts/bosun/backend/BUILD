load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "server",
    srcs = ["server.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//google_genai",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "server_lib",
    srcs = ["server.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//google_genai",
        "@pip//uvicorn",
    ],
)

py_test(
    name = "tts_on_result_test",
    srcs = ["tts_on_result_test.py"],
    imports = ["."],
    deps = [
        "//charts/bosun",
        "//charts/bosun/backend/tests:conftest",
        "@pip//pytest",
        "@pip//starlette",
    ],
)
