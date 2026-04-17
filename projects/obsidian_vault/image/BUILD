load("@rules_apko//apko:defs.bzl", _apko_base = "apko_image")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

# apko base images — kept for MODULE.bazel apko.translate_lock reference.
# The vault-mcp Python server has been removed; these bases are retained
# so that the Bazel module graph remains valid until the lock is cleaned up.

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
