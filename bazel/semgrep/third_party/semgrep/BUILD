load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

bzl_library(
    name = "extensions",
    srcs = ["extensions.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        ":digests",
        "//bazel/semgrep/third_party/semgrep_pro:oci_archive",
    ],
)

# OS+CPU config settings for platform-aware engine selection.
# Shared by both semgrep (OSS) and semgrep_pro BUILD files.
config_setting(
    name = "linux_x86_64",
    constraint_values = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
    visibility = ["//visibility:public"],
)

config_setting(
    name = "linux_aarch64",
    constraint_values = [
        "@platforms//os:linux",
        "@platforms//cpu:aarch64",
    ],
    visibility = ["//visibility:public"],
)

config_setting(
    name = "macos_x86_64",
    constraint_values = [
        "@platforms//os:macos",
        "@platforms//cpu:x86_64",
    ],
    visibility = ["//visibility:public"],
)

config_setting(
    name = "macos_aarch64",
    constraint_values = [
        "@platforms//os:macos",
        "@platforms//cpu:aarch64",
    ],
    visibility = ["//visibility:public"],
)

# Platform-aware alias for the semgrep-core binary
alias(
    name = "engine",
    actual = select({
        ":linux_x86_64": "@semgrep_engine_amd64//:engine",
        ":linux_aarch64": "@semgrep_engine_arm64//:engine",
        ":macos_x86_64": "@semgrep_engine_osx_x86_64//:engine",
        ":macos_aarch64": "@semgrep_engine_osx_arm64//:engine",
    }),
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "digests",
    srcs = ["digests.bzl"],
    visibility = ["//visibility:public"],
)
