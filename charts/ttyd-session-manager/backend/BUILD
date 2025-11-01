load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("@rules_apko//apko:defs.bzl", "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_push")
load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "backend_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/charts/ttyd-session-manager/backend",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_gin_gonic_gin//:go_default_library",
        "@com_github_google_uuid//:uuid",
        "@io_k8s_api//core/v1:core",
        "@io_k8s_apimachinery//pkg/api/resource",
        "@io_k8s_apimachinery//pkg/apis/meta/v1:meta",
        "@io_k8s_client_go//kubernetes",
        "@io_k8s_client_go//rest",
        "@io_k8s_client_go//tools/clientcmd",
    ],
)

go_binary(
    name = "backend",
    embed = [":backend_lib"],
    visibility = ["//visibility:public"],
)

# Backend API server image
go_image(
    name = "image",
    binary = "backend",
)

# TTYD dev environment image with fish shell
apko_image(
    name = "ttyd_image",
    config = "apko.yaml",
    contents = [],
    tag = "latest",
)

platform_transition_filegroup(
    name = "ttyd_image_platform",
    srcs = [":ttyd_image"],
    target_platform = select({
        "@platforms//cpu:arm64": "@rules_go//go/toolchain:linux_arm64",
        "@platforms//cpu:x86_64": "@rules_go//go/toolchain:linux_amd64",
    }),
)

# Create stamped tags file for CI builds
expand_template(
    name = "ttyd_stamped_tags_ci",
    out = "ttyd_stamped_ci.tags.txt",
    template = [
        "{STABLE_BRANCH_TAG}",
        "{STABLE_IMAGE_TAG}",
    ],
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
)

# Create stamped tags file for local builds
expand_template(
    name = "ttyd_stamped_tags_local",
    out = "ttyd_stamped_local.tags.txt",
    template = [
        "{STABLE_IMAGE_TAG}",
    ],
    stamp_substitutions = {
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
)

oci_push(
    name = "ttyd_image.push",
    image = ":ttyd_image_platform",
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd",
    remote_tags = select({
        "//tools/oci:ci_build": ":ttyd_stamped_tags_ci",
        "//conditions:default": ":ttyd_stamped_tags_local",
    }),
    visibility = ["//images:__pkg__"],
)
