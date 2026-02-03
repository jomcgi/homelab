load("@aspect_bazel_lib//lib:copy_to_directory.bzl", "copy_to_directory")
load("@aspect_rules_esbuild//esbuild:defs.bzl", "esbuild")
load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@npm//websites/trips.jomcgi.dev:@tailwindcss/cli/package_json.bzl", tailwind_bin = "bin")
load("@npm//websites/trips.jomcgi.dev:vite/package_json.bzl", vite_bin = "bin")
load("@npm//websites/trips.jomcgi.dev:vitest/package_json.bzl", vitest_bin = "bin")
load("@npm//websites/trips.jomcgi.dev:wrangler/package_json.bzl", wrangler_bin = "bin")

# Trips frontend website - Vite-based React app with Cloudflare Pages deployment
load("//tools/js:tailwind_build.bzl", "tailwind_build")
load("//tools/js:vite_build.bzl", "vite_build")
load("//tools/wrangler:wrangler_pages.bzl", "wrangler_pages")

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

# ==============================================================================
# Alternative esbuild-based build for comparison with Vite
# ==============================================================================
# This build uses esbuild for JS bundling and Tailwind CLI for CSS processing.
# The two outputs are combined into a complete dist for deployment.

# Tailwind CLI binary for CSS processing
tailwind_bin.tailwindcss_binary(name = "tailwindcss")

# JSX source library for esbuild (excludes Vite-specific, test files, and CSS)
js_library(
    name = "esbuild_src",
    srcs = glob(
        [
            "src/**/*.js",
            "src/**/*.jsx",
        ],
        exclude = [
            "src/**/*.test.js",
            "src/**/*.test.jsx",
            "src/test/**/*",
        ],
    ),
    deps = [
        ":node_modules/js-yaml",
        ":node_modules/lucide-react",
        ":node_modules/maplibre-gl",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/suncalc",
        ":node_modules/wouter",
    ],
)

# esbuild bundle
# CSS imports are marked external since Tailwind v4 requires PostCSS processing
esbuild(
    name = "esbuild_js",
    srcs = [":esbuild_src"],
    define = {
        "process.env.NODE_ENV": '"production"',
    },
    entry_point = "src/main-esbuild.jsx",
    external = [
        "*.css",
        "maplibre-gl/dist/maplibre-gl.css",
    ],
    format = "esm",
    minify = True,
    output = "main.js",
    platform = "browser",
    sourcemap = "external",
    target = "es2020",
)

# Tailwind CSS processing - builds index.css with all Tailwind utilities
tailwind_build(
    name = "esbuild_css",
    src = "src/index.css",
    out = "styles.css",
    # Include all JSX files so Tailwind can scan for class usage
    srcs = glob([
        "src/**/*.js",
        "src/**/*.jsx",
    ]),
    tool = ":tailwindcss",
    deps = [":node_modules/tailwindcss"],
)

# Rename index-esbuild.html to index.html for the dist
genrule(
    name = "esbuild_index_html",
    srcs = ["index-esbuild.html"],
    outs = ["_esbuild_index.html"],
    cmd = "cp $< $@",
)

# Assemble esbuild dist directory with all assets in correct structure
# This creates a single output directory suitable for Cloudflare Pages deployment
copy_to_directory(
    name = "esbuild_dist_assembly",
    srcs = [
        ":esbuild_css",
        ":esbuild_index_html",
        ":esbuild_js",
    ] + glob(["public/**/*"]),
    out = "esbuild-dist",
    # Flatten build outputs to root, preserve public/* structure
    replace_prefixes = {
        # Build outputs go to root
        "styles.css": "styles.css",
        "main.js": "main.js",
        "main.js.map": "main.js.map",
        "_esbuild_index.html": "index.html",
        # Public assets: strip public/ prefix
        "public/": "",
    },
    visibility = ["//visibility:public"],
)

# Expose esbuild dist for comparison/deployment
filegroup(
    name = "esbuild_dist",
    srcs = [":esbuild_dist_assembly"],
    visibility = ["//visibility:public"],
)

# Legacy target for compatibility
filegroup(
    name = "esbuild",
    srcs = [":esbuild_dist"],
    visibility = ["//visibility:public"],
)

# Cloudflare Pages deployment for esbuild variant
wrangler_pages(
    name = "trips_esbuild",
    dist = ":esbuild_dist",
    project_name = "trips-jomcgi-dev",
    wrangler = ":wrangler",
)
