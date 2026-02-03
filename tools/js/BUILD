load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

"""JavaScript/Node.js utilities"""

exports_files(
    [
        "esbuild_build.bzl",
        "node_modules_tar.bzl",
        "tailwind_build.bzl",
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
    ],
)

bzl_library(
    name = "esbuild_build",
    srcs = ["esbuild_build.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_rules_esbuild//esbuild:defs",
        "@aspect_rules_js//js:defs",
        "@aspect_rules_ts//ts:defs",
    ],
)

bzl_library(
    name = "tailwind_build",
    srcs = ["tailwind_build.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "@aspect_rules_js//js:defs",
    ],
)
