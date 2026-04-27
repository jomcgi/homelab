# jomcgi.dev website - Astro-based site with React components
load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@npm//projects/websites/jomcgi.dev:astro/package_json.bzl", astro_bin = "bin")
load("@npm//projects/websites/jomcgi.dev:vitest/package_json.bzl", vitest_bin = "bin")
load("@npm//projects/websites/jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")
load("//bazel/tools/js:vite_build.bzl", "vite_build")
load("//bazel/wrangler:defs.bzl", "wrangler_pages")

# Astro binary for building (Astro uses Vite internally)
astro_bin.astro_binary(name = "astro")

# Wrangler binary for Cloudflare Pages deployment
wrangler_bin.wrangler_binary(name = "wrangler")

# Build frontend using unified Vite macro (Astro mode)
vite_build(
    name = "build",
    srcs = glob(
        [
            "src/**/*",
            "public/**/*",
        ],
        allow_empty = True,
        exclude = [
            "src/**/*.test.js",
            "src/**/*.test.jsx",
            "src/**/*.test.ts",
            "src/**/*.test.tsx",
        ],
    ) + [
        "package.json",
        "tailwind.config.mjs",
    ],
    bazel_deps = ["//projects/websites/shared:css"],
    config = "astro.config.mjs",
    tool = ":astro",
    visibility = ["//visibility:public"],
    deps = [
        "astro",
        "astro-remote",
        "mermaid",
        "react",
        "react-dom",
        "reveal.js",
        "tailwindcss",
        "@astrojs/react",
        "@astrojs/tailwind",
    ],
)

# Cloudflare Pages deployment
wrangler_pages(
    name = "jomcgi",
    dist = ":build_dist",
    project_name = "jomcgi-dev",
    visibility = ["//projects/websites:__pkg__"],
    wrangler = ":wrangler",
)

# Test library
js_library(
    name = "test_lib",
    srcs = glob(
        [
            "src/**/*.test.js",
            "src/**/*.test.jsx",
            "src/**/*.test.ts",
            "src/**/*.test.tsx",
        ],
        allow_empty = True,
    ) + [
        "src/test/setup.js",
        "vitest.config.mjs",
    ],
    deps = [
        ":node_modules/@testing-library/jest-dom",
        ":node_modules/@testing-library/react",
        ":node_modules/@testing-library/user-event",
        ":node_modules/happy-dom",
        ":node_modules/vitest",
        ":src",
    ],
)

# Run vitest tests
vitest_bin.vitest_test(
    name = "test",
    args = ["run"],
    chdir = package_name(),
    data = [
        ":src",
        ":test_lib",
    ],
)
