"""Agent Orchestrator UI - Vite + React dashboard + embedded Go library"""

load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//services/agent-orchestrator/ui:vite/package_json.bzl", vite_bin = "bin")
load("@rules_go//go:def.bzl", "go_library")

npm_link_all_packages(name = "node_modules")

vite_bin.vite_binary(name = "vite")

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
        ],
    ) + [
        "index.html",
        "package.json",
        "vite.config.js",
    ],
    deps = [
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/vite",
        ":node_modules/@vitejs/plugin-react",
    ],
)

# Build the Vite app with declared individual file outputs (not out_dirs)
# so that rules_go embedsrcs can pass them to the Go compiler.
# Vite is configured with stable filenames (no content hashes) to make
# the output set predictable.
js_run_binary(
    name = "build",
    srcs = [":src"],
    args = ["build"],
    chdir = native.package_name(),
    outs = [
        "dist/index.html",
        "dist/assets/index.js",
    ],
    tool = ":vite",
)

# Go library that embeds the Bazel-built Vite output.
# The declared outs from :build are individual files under dist/,
# matching the go:embed dist directive in static.go.
go_library(
    name = "ui",
    srcs = ["static.go"],
    embedsrcs = [
        "dist/index.html",
        "dist/assets/index.js",
    ],
    importpath = "github.com/jomcgi/homelab/services/agent-orchestrator/ui",
    visibility = ["//services/agent-orchestrator:__pkg__"],
)
