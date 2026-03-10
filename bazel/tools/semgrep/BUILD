load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")

py_venv_binary(
    name = "upload",
    srcs = ["upload.py"],
    main = "upload.py",
    visibility = ["//visibility:public"],
    deps = ["@pip//httpx"],
)

py_library(
    name = "semgrep",
    srcs = ["upload.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

semgrep_target_test(
    name = "upload_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":upload",
)
