load("@bazel_skylib//:bzl_library.bzl", "bzl_library")
load("@multitool//:tools.bzl", MULTITOOL_TOOLS = "TOOLS")
load("@rules_go//go:def.bzl", "go_library", "go_test")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

exports_files(["render-manifests.sh"])

sh_binary(
    name = "validate_manifests",
    srcs = ["ci-validate-manifests.sh"],
    data = [MULTITOOL_TOOLS["helm"]],
    env = {
        "HELM": "$(rootpath {})".format(MULTITOOL_TOOLS["helm"]),
    },
)

# Sequential shell script version (for reference)
sh_binary(
    name = "render_all",
    srcs = ["render-all-manifests.sh"],
    data = [MULTITOOL_TOOLS["helm"]],
    env = {
        "HELM": "$(rootpath {})".format(MULTITOOL_TOOLS["helm"]),
    },
    visibility = ["//tools/format:__pkg__"],
)

# Gazelle extension for auto-generating BUILD files from ArgoCD applications
go_library(
    name = "argocd",
    srcs = [
        "config.go",
        "generate.go",
        "language.go",
    ],
    importpath = "github.com/jomcgi/homelab/tools/argocd",
    visibility = ["//:__pkg__"],
    deps = [
        "@gazelle//config",
        "@gazelle//label",
        "@gazelle//language",
        "@gazelle//repo",
        "@gazelle//resolve",
        "@gazelle//rule",
        "@io_k8s_sigs_yaml//:yaml",
    ],
)

go_test(
    name = "argocd_test",
    srcs = [
        "config_test.go",
        "generate_test.go",
        "language_test.go",
    ],
    embed = [":argocd"],
    deps = [
        "@gazelle//config",
        "@gazelle//label",
        "@gazelle//rule",
    ],
)

bzl_library(
    name = "defs",
    srcs = ["defs.bzl"],
    visibility = ["//visibility:public"],
    deps = ["@rules_shell//shell:rules_bzl"],
)
