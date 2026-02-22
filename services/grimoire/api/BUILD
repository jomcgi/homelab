load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "api_lib",
    srcs = [
        "campaign.go",
        "character.go",
        "dice.go",
        "encounter.go",
        "feed.go",
        "firestore.go",
        "gemini.go",
        "main.go",
        "middleware.go",
        "rag.go",
        "session.go",
    ],
    importpath = "github.com/jomcgi/homelab/services/grimoire/api",
    visibility = ["//visibility:private"],
    deps = [
        "@com_github_google_generative_ai_go//genai",
        "@com_google_cloud_go_firestore//:firestore",
        "@org_golang_google_api//iterator",
        "@org_golang_google_api//option",
        "@org_golang_google_grpc//codes",
        "@org_golang_google_grpc//status",
        "@org_golang_x_oauth2//google",
    ],
)

go_binary(
    name = "api",
    embed = [":api_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = ":api",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-api",
)
