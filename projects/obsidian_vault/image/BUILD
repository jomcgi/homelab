load("@rules_apko//apko:defs.bzl", _apko_base = "apko_image")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

# --- Per-architecture apko bases (git + bash + busybox) ---
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

# --- Python image on apko base ---
# select() resolves per-arch base via platform_transition_filegroup in py3_image.

py3_image(
    name = "image",
    base = select({
        "@platforms//cpu:arm64": ":git_base_arm64",
        "@platforms//cpu:x86_64": ":git_base_amd64",
    }),
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
