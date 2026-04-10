load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "cdk8s_lib",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "lib_test",
    srcs = ["lib_test.py"],
    deps = [
        ":cdk8s_lib",
        "@pip//pytest",
    ],
)
