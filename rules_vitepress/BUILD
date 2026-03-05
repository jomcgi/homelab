load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

bzl_library(
    name = "defs",
    srcs = ["defs.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "site",
    srcs = ["site.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        ":defs",
        "//rules_wrangler:defs",
        "//tools/js:vite_build",
        "@bazel_skylib//lib:paths",
    ],
)
