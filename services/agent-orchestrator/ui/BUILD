# agent-orchestrator UI — Vite + React SPA embedded in the Go binary.
load("@npm//services/agent-orchestrator/ui:vite/package_json.bzl", vite_bin = "bin")
load("//tools/js:vite_build.bzl", "vite_build")

vite_bin.vite_binary(name = "vite")

vite_build(
    name = "build",
    srcs = glob(
        [
            "src/**/*",
            "public/**/*",
        ],
        allow_empty = True,
    ) + [
        "index.html",
        "package.json",
    ],
    config = "vite.config.js",
    tool = ":vite",
    deps = [
        "@vitejs/plugin-react",
        "react",
        "react-dom",
        "vite",
    ],
    visibility = ["//services/agent-orchestrator:__pkg__"],
)
