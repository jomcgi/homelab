load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

exports_files(["pages_push.sh.tpl"])

# keep: Gazelle's bzl extension mis-resolves these
bzl_library(
    name = "defs",
    srcs = [
        "defs.bzl",  # keep
        "pages.bzl",  # keep
    ],
    visibility = ["//visibility:public"],
    deps = [
        "@bazel_skylib//lib:paths",  # keep
    ],
)
