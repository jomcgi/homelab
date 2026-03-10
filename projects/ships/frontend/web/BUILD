# Ships frontend website - Vite-based React app
load("@aspect_rules_esbuild//esbuild:defs.bzl", "esbuild")
load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//projects/ships/frontend/web:vite/package_json.bzl", vite_bin = "bin")
load("@npm//projects/ships/frontend/web:vitest/package_json.bzl", vitest_bin = "bin")

# Link npm packages for this workspace package
npm_link_all_packages(name = "node_modules")

# Vite binary for building
vite_bin.vite_binary(name = "vite")

# Source files for the Vite build
js_library(
    name = "src",
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
        "vite.config.js",
    ],
    deps = [
        ":node_modules/@vitejs/plugin-react",
        ":node_modules/maplibre-gl",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/vite",
    ],
)

# Run vite build to produce the dist directory
js_run_binary(
    name = "build",
    srcs = [":src"],
    args = ["build"],
    chdir = package_name(),
    out_dirs = ["dist"],
    tool = ":vite",
)

# Expose the built dist for packaging into container
filegroup(
    name = "dist",
    srcs = [":build"],
    visibility = ["//projects/ships/frontend:__pkg__"],
)

# Test files
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

# Alternative esbuild-based build for comparison with Vite
# JSX source library (without Vite-specific files)
js_library(
    name = "esbuild_src",
    srcs = glob(
        ["src/**/*.jsx"],
        exclude = [
            "src/**/*.test.jsx",
        ],
    ) + glob(["src/**/*.css"]),
    deps = [
        ":node_modules/maplibre-gl",
        ":node_modules/react",
        ":node_modules/react-dom",
    ],
)

# esbuild bundle
esbuild(
    name = "esbuild",
    srcs = [":esbuild_src"],
    define = {
        "process.env.NODE_ENV": '"production"',
    },
    entry_point = "src/main.jsx",
    format = "esm",
    minify = True,
    platform = "browser",
    sourcemap = "external",
    target = "es2020",
)

# Expose esbuild dist for comparison
filegroup(
    name = "esbuild_dist",
    srcs = [
        "public/favicon.svg",
        "src/index.css",
        ":esbuild",
    ],
)
