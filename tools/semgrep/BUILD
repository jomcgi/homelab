load("@rules_python//python:py_binary.bzl", "py_binary")
load("@rules_python//python/entry_points:py_console_script_binary.bzl", "py_console_script_binary")

py_console_script_binary(
    name = "semgrep",
    pkg = "@pip//semgrep",
    visibility = ["//visibility:public"],
)

# osemgrep (the native engine inside semgrep) execs pysemgrep at runtime.
# Both must be available on PATH for semgrep to work in sandboxed tests.
py_console_script_binary(
    name = "pysemgrep",
    pkg = "@pip//semgrep",
    visibility = ["//visibility:public"],
)

py_binary(
    name = "upload",
    srcs = ["upload.py"],
    visibility = ["//visibility:public"],
    deps = ["@pip//httpx"],
)
