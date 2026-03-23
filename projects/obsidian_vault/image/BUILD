load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_apko//apko:defs.bzl", _apko_base = "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_image_index")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

# --- Multi-platform apko base (git + bash + busybox) ---
# py3_image provides hermetic Python; apko provides git for vault sync.

_apko_base(
    name = "git_base_amd64",
    architecture = "x86_64",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    tag = "latest",
)

_apko_base(
    name = "git_base_arm64",
    architecture = "aarch64",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    tag = "latest",
)

platform_transition_filegroup(
    name = "git_base_amd64_transitioned",
    srcs = [":git_base_amd64"],
    target_platform = "//bazel/tools/platforms:linux_x86_64",
)

platform_transition_filegroup(
    name = "git_base_arm64_transitioned",
    srcs = [":git_base_arm64"],
    target_platform = "//bazel/tools/platforms:linux_aarch64",
)

oci_image_index(
    name = "git_base",
    images = [
        ":git_base_amd64_transitioned",
        ":git_base_arm64_transitioned",
    ],
)

# --- Python image on apko base ---

py3_image(
    name = "image",
    base = ":git_base",
    binary = "//projects/obsidian_vault/vault_mcp/app:main",
    env = {
        "GIT_SSH_COMMAND": "ssh -o StrictHostKeyChecking=no",
        "HOME": "/home/vault",
        "TZ": "Europe/Dublin",
    },
    main = "main.py",
    repository = "ghcr.io/jomcgi/homelab/projects/obsidian_vault/image",
)

# Verify lock file is in sync with config
sh_test(
    name = "image_lock_test",
    srcs = ["//bazel/tools/oci:verify-apko-lock.sh"],
    args = [
        "$(location apko.yaml)",
        "$(location apko.lock.json)",
    ],
    data = [
        "apko.lock.json",
        "apko.yaml",
    ],
)
