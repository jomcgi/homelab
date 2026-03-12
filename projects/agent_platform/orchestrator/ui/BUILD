"""Agent Orchestrator UI - Vite + React dashboard + embedded Go library"""

load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//projects/agent_platform/orchestrator/ui:vite/package_json.bzl", vite_bin = "bin")
load("@rules_go//go:def.bzl", "go_library")
load("//bazel/tools/js:vite_build.bzl", "vite_build")

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
        "react-markdown",
        "vite",
        "@vitejs/plugin-react",
    ],
)

# Go library that embeds the Bazel-built Vite output (dist/).
# The vite_build target builds the React dashboard; its tree artifact
# is embedded at compile time via go:embed.
go_library(
    name = "ui",
    srcs = ["static.go"],
    embedsrcs = [":build"],
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/orchestrator/ui",
    visibility = ["//projects/agent_platform/orchestrator:__pkg__"],
)
