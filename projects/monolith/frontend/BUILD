# gazelle:ignore
load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//projects/monolith/frontend:vite/package_json.bzl", vite_bin = "bin")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

npm_link_all_packages(name = "node_modules")

vite_bin.vite_binary(name = "vite")

js_library(
    name = "src",
    srcs = glob(
        [
            "src/**/*",
            "static/**/*",
        ],
        allow_empty = True,
    ) + [
        "package.json",
        "svelte.config.js",
        "vite.config.js",
    ],
    deps = [
        ":node_modules/@sveltejs/adapter-node",
        ":node_modules/@sveltejs/kit",
        ":node_modules/@sveltejs/vite-plugin-svelte",
        ":node_modules/mdsvex",
        ":node_modules/svelte",
        ":node_modules/vite",
        # Platform-specific native binaries for Linux CI (loaded at runtime via require())
        ":node_modules/@rollup/rollup-linux-x64-gnu",
        ":node_modules/@esbuild/linux-x64",
    ],
)

js_run_binary(
    name = "build",
    srcs = [":src"],
    args = ["build"],
    chdir = package_name(),
    out_dirs = ["build"],
    tool = ":vite",
    visibility = ["//projects/monolith:__pkg__"],
)

# Validate the frontend builds in CI without going through py3_image's
# platform transition (which breaks native npm packages like esbuild/rollup).
build_test(
    name = "build_test",
    targets = [":build"],
)

genrule(
    name = "build_tar",
    srcs = [":build"],
    outs = ["build_tar.tar"],
    cmd = """
        set -euo pipefail
        mkdir -p tmp/app/build
        cp -rL $(location :build)/* tmp/app/build/
        tar -C tmp -cf $@ .
    """,
)

apko_image(
    name = "image",
    config = "//projects/monolith/frontend:image.yaml",
    contents = "@monolith_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/frontend",
    tars = [":build_tar"],
)
