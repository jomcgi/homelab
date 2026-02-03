load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

# Export push template for wrangler_pages rule
exports_files(
    ["wrangler_push.sh.tpl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "wrangler_pages",
    srcs = ["wrangler_pages.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@bazel_skylib//lib:paths"],
)
