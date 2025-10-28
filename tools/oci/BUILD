load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

# no targets in this package

bzl_library(
    name = "go_image",
    srcs = ["go_image.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_bazel_lib//lib:tar",
        "@aspect_bazel_lib//lib:transitions",
        "@rules_oci//oci:defs",
    ],
)

bzl_library(
    name = "py3_image",
    srcs = ["py3_image.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_bazel_lib//lib:transitions",
        "@aspect_rules_py//py:defs",
        "@rules_oci//oci:defs",
    ],
)
