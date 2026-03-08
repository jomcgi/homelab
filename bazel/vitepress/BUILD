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
        "//bazel/tools/js:vite_build",
        "//bazel/wrangler:defs",
        "@bazel_skylib//lib:paths",
    ],
)
