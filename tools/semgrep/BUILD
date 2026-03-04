load("@rules_python//python:py_binary.bzl", "py_binary")

py_binary(
    name = "upload",
    srcs = ["upload.py"],
    visibility = ["//visibility:public"],
    deps = ["@pip//httpx"],
)
