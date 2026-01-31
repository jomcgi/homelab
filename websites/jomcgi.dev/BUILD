# jomcgi.dev website - Astro-based site with React components
load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//websites/jomcgi.dev:vitest/package_json.bzl", vitest_bin = "bin")

# Link npm packages for this workspace package
npm_link_all_packages(name = "node_modules")

# Source files
js_library(
    name = "src",
    srcs = glob(
        [
            "src/**/*",
            "public/**/*",
        ],
        exclude = [
            "src/**/*.test.js",
            "src/**/*.test.jsx",
            "src/**/*.test.ts",
            "src/**/*.test.tsx",
        ],
        allow_empty = True,
    ) + [
        "package.json",
        "astro.config.mjs",
        "tailwind.config.mjs",
    ],
    deps = [
        ":node_modules/@astrojs/react",
        ":node_modules/@astrojs/tailwind",
        ":node_modules/astro",
        ":node_modules/astro-remote",
        ":node_modules/mermaid",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/reveal.js",
        ":node_modules/tailwindcss",
    ],
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
        "vitest.config.mjs",
        "src/test/setup.js",
    ],
    deps = [
        ":src",
        ":node_modules/@testing-library/jest-dom",
        ":node_modules/@testing-library/react",
        ":node_modules/@testing-library/user-event",
        ":node_modules/happy-dom",
        ":node_modules/vitest",
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
