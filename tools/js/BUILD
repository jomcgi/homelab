load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

"""JavaScript/Node.js utilities"""

exports_files(
    [
        "node_modules_tar.bzl",
        "vite_build.bzl",
    ],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "node_modules_tar",
    srcs = ["node_modules_tar.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "vite_build",
    srcs = ["vite_build.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_rules_js//js:defs",
        "@npm//:defs",
    ],
)
