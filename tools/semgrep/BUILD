load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@rules_python//python:py_binary.bzl", "py_binary")
load("//rules_semgrep:defs.bzl", "semgrep_test")

py_binary(
    name = "upload",
    srcs = ["upload.py"],
    visibility = ["//visibility:public"],
    deps = ["@pip//httpx"],
)

semgrep_test(
    name = "upload_semgrep_test",
    srcs = ["upload.py"],
    rules = ["//semgrep_rules:python_rules"],
)

py_library(
    name = "semgrep",
    srcs = ["upload.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)
