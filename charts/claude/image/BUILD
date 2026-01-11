load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the compiled TypeScript API server
# Note: src/dist/ must be built first: cd charts/claude/src && pnpm build
pkg_tar(
    name = "app_tar",
    srcs = [
        "start.sh",
        "//charts/claude/src:dist",
        "//charts/claude/src:package.json",
    ],
    mode = "0755",
    remap_paths = {
        "src/dist": "/app/dist",
        "src/package.json": "/app/package.json",
        "start.sh": "/app/start.sh",
    },
    strip_prefix = "charts/claude",
)

# Package the compiled frontend
# Note: frontend/dist/ must be built first: cd charts/claude/frontend && pnpm build
pkg_tar(
    name = "frontend_tar",
    srcs = ["//charts/claude/frontend:dist"],
    mode = "0644",
    remap_paths = {
        "frontend/dist": "/app/public",
    },
    strip_prefix = "charts/claude",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@claude_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/claude",
    tars = [
        ":app_tar",
        ":frontend_tar",
    ],
)
