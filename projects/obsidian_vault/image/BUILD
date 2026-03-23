load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@aspect_rules_py//py:defs.bzl", "py_image_layer")
load("@rules_apko//apko:defs.bzl", _apko_base = "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//bazel/tools/oci:providers.bzl", "oci_image_info")

_BINARY = "//projects/obsidian_vault/vault_mcp/app:main"
_BINARY_PATH = "/projects/obsidian_vault/vault_mcp/app/main"
_RUNFILES = _BINARY_PATH + ".runfiles"
_WORKSPACE = _RUNFILES + "/_main"
_REPOSITORY = "ghcr.io/jomcgi/homelab/projects/obsidian_vault/image"

_ENV = {
    "BAZEL_WORKSPACE": "_main",
    "RUNFILES_DIR": _RUNFILES,
    "PYTHONPATH": _WORKSPACE,
}

# --- Per-architecture apko bases (Python 3.12 + git) ---

_apko_base(
    name = "base_amd64",
    architecture = "x86_64",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    tag = "latest",
)

_apko_base(
    name = "base_arm64",
    architecture = "aarch64",
    config = "apko.yaml",
    contents = "@obsidian_vault_lock//:contents",
    tag = "latest",
)

# --- Python application layers ---

_LAYERS_AMD64 = py_image_layer(
    name = "layers_amd64",
    binary = _BINARY,
    root = "/",
)

_LAYERS_ARM64 = py_image_layer(
    name = "layers_arm64",
    binary = _BINARY,
    root = "/",
)

# Main source file (py_venv_binary omits main.py from runfiles)
tar(
    name = "main_src_tar",
    srcs = ["//projects/obsidian_vault/vault_mcp/app:main.py"],
    mtree = [
        ".%s/projects/obsidian_vault/vault_mcp/app/main.py type=file content=$(execpath //projects/obsidian_vault/vault_mcp/app:main.py)" % _WORKSPACE,
    ],
)

# --- Per-architecture final images ---

oci_image(
    name = "image_amd64",
    base = ":base_amd64",
    entrypoint = [_BINARY_PATH],
    env = _ENV,
    tars = _LAYERS_AMD64 + [":main_src_tar"],
)

platform_transition_filegroup(
    name = "image_amd64_transitioned",
    srcs = [":image_amd64"],
    target_platform = "//bazel/tools/platforms:linux_x86_64",
)

oci_image(
    name = "image_arm64",
    base = ":base_arm64",
    entrypoint = [_BINARY_PATH],
    env = _ENV,
    tars = _LAYERS_ARM64 + [":main_src_tar"],
)

platform_transition_filegroup(
    name = "image_arm64_transitioned",
    srcs = [":image_arm64"],
    target_platform = "//bazel/tools/platforms:linux_aarch64",
)

# --- Multi-platform index ---

oci_image_index(
    name = "image",
    images = [
        ":image_amd64_transitioned",
        ":image_arm64_transitioned",
    ],
)

# --- Push, info, and test targets ---

expand_template(
    name = "image_stamped_tags_ci",
    out = "image_stamped_ci.tags.txt",
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = [
        "{STABLE_IMAGE_TAG}",
        "{STABLE_BRANCH_TAG}",
    ],
)

expand_template(
    name = "image_stamped_tags_local",
    out = "image_stamped_local.tags.txt",
    stamp_substitutions = {
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = [
        "{STABLE_IMAGE_TAG}",
    ],
)

oci_push(
    name = "image.push",
    image = ":image",
    remote_tags = select({
        "//bazel/tools/oci:ci_build": "image_stamped_tags_ci",
        "//conditions:default": "image_stamped_tags_local",
    }),
    repository = _REPOSITORY,
    visibility = ["//bazel/images:__pkg__"],
)

oci_image_info(
    name = "image.info",
    image_tags = "image_stamped_ci.tags.txt",
    repository = _REPOSITORY,
    visibility = ["//visibility:public"],
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

# Verify Python runtime config (PYTHONPATH, RUNFILES_DIR, entrypoint)
sh_test(
    name = "image_config_test",
    srcs = ["//bazel/tools/oci:verify-py3-image.sh"],
    args = ["$(rootpath :image_amd64)"],
    data = [":image_amd64"],
)
