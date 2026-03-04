load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

exports_files([
    "semgrep-test.sh",
    "semgrep-manifest-test.sh",
])

# keep: Gazelle's bzl extension mis-resolves @rules_shell//shell:sh_test.bzl
bzl_library(
    name = "defs",
    srcs = [
        "defs.bzl",  # keep
        "test.bzl",  # keep
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":target_test",
        "@rules_shell//shell:rules_bzl",  # keep
    ],
)

# keep: Gazelle mis-resolves @rules_shell//shell:sh_test.bzl
bzl_library(
    name = "test",
    srcs = ["test.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@rules_shell//shell:rules_bzl"],  # keep
)

bzl_library(
    name = "aspect",
    srcs = ["aspect.bzl"],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "target_test",
    srcs = ["target_test.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        ":aspect",
        "@rules_shell//shell:rules_bzl",  # keep
    ],
)
