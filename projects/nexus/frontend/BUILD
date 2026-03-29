load("@npm//projects/nexus/frontend:vite/package_json.bzl", vite_bin = "bin")
load("//bazel/tools/js:vite_build.bzl", "vite_build")

# Vite binary for building (SvelteKit uses Vite internally)
vite_bin.vite_binary(name = "vite")

# Build SvelteKit frontend as static site
vite_build(
    name = "build",
    srcs = glob(
        [
            "src/**/*",
            "static/**/*",
        ],
        allow_empty = True,
        exclude = [
            "src/**/*.test.js",
            "src/**/*.test.ts",
        ],
    ) + [
        "package.json",
        "svelte.config.js",
    ],
    tool = ":vite",
    visibility = ["//visibility:public"],
    deps = [
        "@sveltejs/adapter-static",
        "@sveltejs/kit",
        "@sveltejs/vite-plugin-svelte",
        "mdsvex",
        "svelte",
        "vite",
    ],
)
