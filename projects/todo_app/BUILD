load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "todo_app",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

filegroup(
    name = "static_files",
    srcs = glob(["static/**"]),
    visibility = ["//projects/todo_app/image:__pkg__"],
)

py3_image(
    name = "py_image",
    binary = "//projects/todo_app/todo_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/projects/todo_app",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
