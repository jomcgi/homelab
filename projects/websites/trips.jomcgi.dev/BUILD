load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@npm//projects/websites/trips.jomcgi.dev:vite/package_json.bzl", vite_bin = "bin")
load("@npm//projects/websites/trips.jomcgi.dev:vitest/package_json.bzl", vitest_bin = "bin")
load("@npm//projects/websites/trips.jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")
load("//bazel/tools/js:vite_build.bzl", "vite_build")
load("//bazel/wrangler:defs.bzl", "wrangler_pages")

# Vite binary for building (required by vite_build macro)
vite_bin.vite_binary(name = "vite")

# Wrangler binary for Cloudflare Pages deployment
wrangler_bin.wrangler_binary(name = "wrangler")

# Build frontend using unified Vite macro
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
        "index.html",
        "package.json",
        "postcss.config.js",
    ],
    tool = ":vite",
    visibility = ["//visibility:public"],
    deps = [
        "autoprefixer",
        "js-yaml",
        "lucide-react",
        "maplibre-gl",
        "postcss",
        "react",
        "react-dom",
        "suncalc",
        "tailwindcss",
        "vite",
        "wouter",
        "@tailwindcss/postcss",
        "@vitejs/plugin-react",
    ],
)

# Cloudflare Pages deployment
wrangler_pages(
    name = "trips",
    dist = ":build_dist",
    project_name = "trips-jomcgi-dev",
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
        "vitest.config.js",
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
