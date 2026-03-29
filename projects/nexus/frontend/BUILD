# gazelle:ignore
load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//projects/nexus/frontend:vite/package_json.bzl", vite_bin = "bin")

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
        ":node_modules/@sveltejs/adapter-static",
        ":node_modules/@sveltejs/kit",
        ":node_modules/@sveltejs/vite-plugin-svelte",
        ":node_modules/mdsvex",
        ":node_modules/svelte",
        ":node_modules/vite",
        # Rollup's platform-specific native binary for Linux CI (loaded at runtime via require())
        ":node_modules/@rollup/rollup-linux-x64-gnu",
    ],
)

js_run_binary(
    name = "build",
    srcs = [":src"],
    args = ["build"],
    chdir = package_name(),
    out_dirs = ["dist"],
    tool = ":vite",
    visibility = ["//projects/nexus/backend:__pkg__"],
)
