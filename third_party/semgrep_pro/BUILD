load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

bzl_library(
    name = "extensions",
    srcs = ["extensions.bzl"],
    visibility = ["//visibility:public"],
    deps = [":oci_archive"],
)

# Platform-aware alias for the pro engine binary
alias(
    name = "engine",
    actual = select({
        "@platforms//cpu:x86_64": "@semgrep_pro_engine_amd64//:engine",
        "@platforms//cpu:aarch64": "@semgrep_pro_engine_arm64//:engine",
    }),
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "digests",
    srcs = ["digests.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "oci_archive",
    srcs = ["oci_archive.bzl"],
    visibility = ["//visibility:public"],
)
