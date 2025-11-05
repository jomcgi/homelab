load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

# Detect CI builds to conditionally apply branch tags
config_setting(
    name = "ci_build",
    values = {"define": "CI=true"},
    visibility = ["//visibility:public"],
)

# Export push template for apko_push rule
exports_files(
    ["apko_push.sh.tpl"],
    visibility = ["//visibility:public"],
)

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

bzl_library(
    name = "apko_image",
    srcs = ["apko_image.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        ":apko_push",
        ":oci_run",
        "@aspect_bazel_lib//lib:expand_template",
        "@aspect_bazel_lib//lib:transitions",
        "@rules_apko//apko:defs",
        "@rules_oci//oci:defs",
    ],
)

bzl_library(
    name = "apko_push",
    srcs = ["apko_push.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@bazel_skylib//lib:paths"],
)

bzl_library(
    name = "multiarch_binary_from_http",
    srcs = ["multiarch_binary_from_http.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@rules_pkg//pkg:tar"],
)

bzl_library(
    name = "multiarch_binary_tar",
    srcs = ["multiarch_binary_tar.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@rules_pkg//pkg:tar"],
)

bzl_library(
    name = "multiplatform_tar",
    srcs = ["multiplatform_tar.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@rules_pkg//pkg:tar"],
)

bzl_library(
    name = "oci_run",
    srcs = ["oci_run.bzl"],
    visibility = ["//visibility:public"],
)
