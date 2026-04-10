# gazelle:exclude **
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    data = ["main.py"],
    deps = [
        "//bazel/tools/cdk8s/lib:cdk8s_lib",
        "@pip//pytest",
    ],
)
