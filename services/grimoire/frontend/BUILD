"Grimoire frontend - Vite-based React + TypeScript app"

load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//services/grimoire/frontend:vite/package_json.bzl", vite_bin = "bin")

npm_link_all_packages(name = "node_modules")

vite_bin.vite_binary(name = "vite")

js_library(
    name = "src",
    srcs = glob(
        [
            "src/**/*",
        ],
        exclude = [
            "src/**/*.test.*",
        ],
    ) + [
        "index.html",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
    ],
    deps = [
        ":node_modules/@tanstack/react-query",
        ":node_modules/@tanstack/react-router",
        ":node_modules/@vitejs/plugin-react",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/vite",
        ":node_modules/zustand",
    ],
)

js_run_binary(
    name = "build",
    srcs = [":src"],
    args = ["build"],
    chdir = package_name(),
    out_dirs = ["dist"],
    tool = ":vite",
)

filegroup(
    name = "dist",
    srcs = [":build"],
    visibility = ["//charts/grimoire:__subpackages__"],
)
