"Bosun backend: apko base (system tools) + py_image_layer (pip deps) + scripts + ttyd"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@aspect_rules_py//py:defs.bzl", "py_image_layer")
load("@rules_apko//apko:defs.bzl", apko = "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

# ── Shell scripts tar (platform-independent) ─────────────────────
pkg_tar(
    name = "app_scripts_tar",
    srcs = [
        "git-sync.sh",
        "start.sh",
    ],
    mode = "0755",
    owner = "1000.1000",
    package_dir = "app",
)

# ── Per-arch apko bases (system tools + Python runtime) ──────────
apko(
    name = "base_amd64",
    architecture = "x86_64",
    config = "apko.yaml",
    contents = "@bosun_backend_lock//:contents",
    tag = "latest",
)

apko(
    name = "base_arm64",
    architecture = "aarch64",
    config = "apko.yaml",
    contents = "@bosun_backend_lock//:contents",
    tag = "latest",
)

platform_transition_filegroup(
    name = "base_amd64_transitioned",
    srcs = [":base_amd64"],
    target_platform = "@rules_go//go/toolchain:linux_amd64",
)

platform_transition_filegroup(
    name = "base_arm64_transitioned",
    srcs = [":base_arm64"],
    target_platform = "@rules_go//go/toolchain:linux_arm64",
)

# ── AMD64 image: apko base + pip deps + scripts + ttyd ───────────
oci_image(
    name = "image_base_amd64",
    base = ":base_amd64_transitioned",
    entrypoint = ["/app/start.sh"],
    tars = py_image_layer(
        name = "py_layers_amd64",
        binary = "//charts/bosun/backend:server",
        root = "/",
    ) + [
        ":app_scripts_tar",
        "@ttyd//:tar_amd64",
    ],
)

platform_transition_filegroup(
    name = "image_amd64",
    srcs = [":image_base_amd64"],
    target_platform = "//tools/platforms:linux_x86_64",
)

# ── ARM64 image: apko base + pip deps + scripts + ttyd ───────────
oci_image(
    name = "image_base_arm64",
    base = ":base_arm64_transitioned",
    entrypoint = ["/app/start.sh"],
    tars = py_image_layer(
        name = "py_layers_arm64",
        binary = "//charts/bosun/backend:server",
        root = "/",
    ) + [
        ":app_scripts_tar",
        "@ttyd//:tar_arm64",
    ],
)

platform_transition_filegroup(
    name = "image_arm64",
    srcs = [":image_base_arm64"],
    target_platform = "//tools/platforms:linux_aarch64",
)

# ── Multi-platform image index ───────────────────────────────────
oci_image_index(
    name = "image",
    images = [
        ":image_amd64",
        ":image_arm64",
    ],
)

# ── Stamped tags ─────────────────────────────────────────────────
expand_template(
    name = "image_stamped_tags_ci",
    out = "image_stamped_ci.tags.txt",
    stamp_substitutions = {
        "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
        "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
    },
    template = [
        "{STABLE_BRANCH_TAG}",
        "{STABLE_IMAGE_TAG}",
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

# ── Push target ──────────────────────────────────────────────────
oci_push(
    name = "image.push",
    image = ":image",
    remote_tags = select({
        "//tools/oci:ci_build": "image_stamped_tags_ci",
        "//conditions:default": "image_stamped_tags_local",
    }),
    repository = "ghcr.io/jomcgi/homelab/charts/bosun/backend",
    visibility = ["//images:__pkg__"],
)
