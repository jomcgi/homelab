"Grimoire frontend - Vite-based React + TypeScript app"

load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//services/grimoire/frontend:vite/package_json.bzl", vite_bin = "bin")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

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

# Package Vite build output into /usr/share/nginx/html
pkg_tar(
    name = "dist_tar",
    srcs = [":dist"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "usr/share/nginx/html",
    strip_prefix = "services/grimoire/frontend/dist",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@grimoire_frontend_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-frontend",
    tars = [
        ":dist_tar",
    ],
)
