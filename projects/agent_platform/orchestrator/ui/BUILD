"""Agent Orchestrator UI - Vite + React dashboard"""

load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//projects/agent_platform/orchestrator/ui:vite/package_json.bzl", vite_bin = "bin")
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
    visibility = ["//projects/agent_platform/orchestrator:__pkg__"],
    deps = [
        "react",
        "react-dom",
        "vite",
        "@vitejs/plugin-react",
    ],
)
