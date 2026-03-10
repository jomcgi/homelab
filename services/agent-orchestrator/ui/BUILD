"""Agent Orchestrator UI - Vite + React dashboard + embedded Go library"""

load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//services/agent-orchestrator/ui:vite/package_json.bzl", vite_bin = "bin")
load("@rules_go//go:def.bzl", "go_library")
load("//tools/js:vite_build.bzl", "vite_build")

npm_link_all_packages(name = "node_modules")

vite_bin.vite_binary(name = "vite")

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
        ],
    ) + [
        "index.html",
        "package.json",
    ],
    config = "vite.config.js",
    tool = ":vite",
    deps = [
        "react",
        "react-dom",
        "@vitejs/plugin-react",
    ],
)

# Go library that embeds the Vite build output.
# embedsrcs must be in the same Bazel package as the go_library.
go_library(
    name = "ui",
    srcs = ["static.go"],
    embedsrcs = [":build_dist"],  # keep
    importpath = "github.com/jomcgi/homelab/services/agent-orchestrator/ui",
    visibility = ["//services/agent-orchestrator:__pkg__"],
)
