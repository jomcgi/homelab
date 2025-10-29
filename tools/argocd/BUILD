"""ArgoCD diff tooling using snapshot-based clusters."""

load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

sh_binary(
    name = "diff",
    srcs = ["diff.sh"],
    visibility = ["//visibility:public"],
)

sh_binary(
    name = "create_snapshot",
    srcs = ["//scripts:create-argocd-snapshot.sh"],
    visibility = ["//visibility:public"],
)
