load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "syncer_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/charts/n8n/syncer",
    visibility = ["//visibility:private"],
    deps = [
        "//charts/n8n/syncer/internal/sync",
        "//charts/n8n/syncer/internal/telemetry",
        "//pkg/n8n",
    ],
)

go_binary(
    name = "syncer",
    embed = [":syncer_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = "syncer",
)
