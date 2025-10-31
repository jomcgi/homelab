load("@bazel_skylib//:bzl_library.bzl", "bzl_library")

"""ArgoCD diff tooling using snapshot-based clusters."""

load("@multitool//:tools.bzl", MULTITOOL_TOOLS = "TOOLS")
load("@rules_go//go:def.bzl", "go_library")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

# Export scripts so Gazelle-generated targets can reference them
exports_files(
    [
        "diff.sh",
        "argocd-live-diff.sh",
        "render-manifests.sh",
    ],
    visibility = ["//overlays:__subpackages__"],
)

sh_binary(
    name = "diff",
    srcs = ["diff.sh"],
)

sh_binary(
    name = "login",
    srcs = ["argocd-login.sh"],
    data = [
        MULTITOOL_TOOLS["argocd"],
        MULTITOOL_TOOLS["op"],
    ],
    env = {
        "ARGOCD": "$(rootpath {})".format(MULTITOOL_TOOLS["argocd"]),
        "OP": "$(rootpath {})".format(MULTITOOL_TOOLS["op"]),
    },
)

sh_binary(
    name = "create_snapshot",
    srcs = ["create-argocd-snapshot.sh"],
    data = [MULTITOOL_TOOLS["kind"]],
    env = {
        "KIND": "$(rootpath {})".format(MULTITOOL_TOOLS["kind"]),
    },
)

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

bzl_library(
    name = "defs",
    srcs = ["defs.bzl"],
    visibility = ["//visibility:public"],
)
