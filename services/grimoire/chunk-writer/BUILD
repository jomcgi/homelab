load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "chunk-writer_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/services/grimoire/chunk-writer",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
        "@com_google_cloud_go_firestore//:firestore",
    ],
)

go_binary(
    name = "chunk-writer",
    embed = [":chunk-writer_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = ":chunk-writer",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-chunk-writer",
)
