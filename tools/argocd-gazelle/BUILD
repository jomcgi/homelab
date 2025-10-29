"""ArgoCD Gazelle extension for auto-generating BUILD files."""

load("@rules_go//go:def.bzl", "go_library")

# Gazelle extension for auto-generating BUILD files from ArgoCD applications
go_library(
    name = "argocd-gazelle",
    srcs = [
        "language.go",
        "config.go",
        "generate.go",
    ],
    importpath = "github.com/jomcgi/homelab/tools/argocd-gazelle",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel_gazelle//config:go_default_library",
        "@bazel_gazelle//label:go_default_library",
        "@bazel_gazelle//language:go_default_library",
        "@bazel_gazelle//rule:go_default_library",
        "@io_k8s_sigs_yaml//:yaml",
    ],
)
