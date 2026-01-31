# Trips frontend website - Vite-based React app
load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//websites/trips.jomcgi.dev:vite/package_json.bzl", vite_bin = "bin")
load("@npm//websites/trips.jomcgi.dev:vitest/package_json.bzl", vitest_bin = "bin")

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
        "postcss.config.js",
        "vite.config.js",
    ],
    deps = [
        ":node_modules/@vitejs/plugin-react",
        ":node_modules/js-yaml",
        ":node_modules/lucide-react",
        ":node_modules/maplibre-gl",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/suncalc",
        ":node_modules/vite",
        ":node_modules/wouter",
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
