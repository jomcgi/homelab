load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Goose config into the image at ~/.config/goose/config.yaml
pkg_tar(
    name = "config_tar",
    srcs = ["config.yaml"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/.config/goose",
)

# Package Goose recipes into the image at ~/recipes/
pkg_tar(
    name = "recipes_tar",
    srcs = glob(["recipes/*.yaml"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/recipes",
)

# Cross-compile runner binary for amd64
platform_transition_filegroup(
    name = "runner_amd64_bin",
    srcs = ["//services/agent-orchestrator/cmd/runner"],
    target_platform = "@rules_go//go/toolchain:linux_amd64",
)

# Package runner binary for amd64
tar(
    name = "runner_tar_amd64",
    srcs = [":runner_amd64_bin"],
    mtree = [
        "./usr/local/bin/agent-runner type=file content=$(execpath :runner_amd64_bin) mode=0755 uid=0 gid=0",
    ],
)

# Cross-compile runner binary for arm64
platform_transition_filegroup(
    name = "runner_arm64_bin",
    srcs = ["//services/agent-orchestrator/cmd/runner"],
    target_platform = "@rules_go//go/toolchain:linux_arm64",
)

# Package runner binary for arm64
tar(
    name = "runner_tar_arm64",
    srcs = [":runner_arm64_bin"],
    mtree = [
        "./usr/local/bin/agent-runner type=file content=$(execpath :runner_arm64_bin) mode=0755 uid=0 gid=0",
    ],
)

# Build the goose-agent image:
#   apko base: bash, git, coreutils (from Wolfi) — minimal runtime
#   multiarch tars: goose binary, agent-runner
#   regular tars: Goose config, recipes
# Dev tools (go, node, claude, bb, formatters) are provided via OCI volume mount
# from the homelab-tools image — see charts/goose-sandboxes/values.yaml.
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@goose_agent_lock//:contents",
    multiarch_tars = [
        "@goose//:tar",
        ":runner_tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/goose-agent",
    tars = [
        ":config_tar",
        ":recipes_tar",
    ],
)
