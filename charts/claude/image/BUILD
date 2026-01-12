load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# OpenCode configuration for vLLM and provider access
# Stored in /etc/opencode/ because /home/user is a PVC mount
# start.sh copies this to ~/.config/opencode/ at runtime
pkg_tar(
    name = "opencode_config_tar",
    srcs = [
        "opencode.json",
    ],
    mode = "0644",
    remap_paths = {
        "opencode.json": "/etc/opencode/opencode.json",
    },
)

# Package start.sh at /app/
pkg_tar(
    name = "app_base_tar",
    srcs = [
        "start.sh",
    ],
    mode = "0755",
    owner = "1000.1000",
    package_dir = "app",
)

# Package the CUI frontend source for runtime build
# CUI is a complete Express server with React frontend
# Use strip_prefix="." to preserve directory structure from the source package
pkg_tar(
    name = "frontend_tar",
    srcs = ["//charts/claude/frontend:src"],
    mode = "0644",
    owner = "1000.1000",
    package_dir = "app/frontend",
    strip_prefix = ".",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@claude_lock//:contents",
    multiarch_tars = [
        "@opencode//:tar",
        "@ttyd//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/charts/claude",
    tars = [
        ":app_base_tar",
        ":frontend_tar",
        ":opencode_config_tar",
    ],
)
