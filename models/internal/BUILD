# gazelle:ignore
load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

bzl_library(
    name = "gguf",
    srcs = ["gguf.bzl"],
    visibility = ["//models:__subpackages__"],
)

bzl_library(
    name = "hf_model",
    srcs = ["hf_model.bzl"],
    visibility = ["//models:__subpackages__"],
)

bzl_library(
    name = "safetensors",
    srcs = ["safetensors.bzl"],
    visibility = ["//models:__subpackages__"],
)
