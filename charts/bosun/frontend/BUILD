"Bosun frontend - Vite-based React app"

load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@npm//:defs.bzl", "npm_link_all_packages")
load("@npm//charts/bosun/frontend:vite/package_json.bzl", vite_bin = "bin")

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
        ],
        exclude = [
            "src/**/*.test.*",
        ],
    ) + [
        "index.html",
        "package.json",
        "vite.config.js",
    ],
    deps = [
        ":node_modules/@vitejs/plugin-react",
        ":node_modules/lucide-react",
        ":node_modules/marked",
        ":node_modules/mermaid",
        ":node_modules/react",
        ":node_modules/react-dom",
        ":node_modules/vite",
        # Transitive deps of mermaid → langium/chevrotain that Rollup needs to resolve
        ":node_modules/@chevrotain/regexp-to-ast",
        ":node_modules/chevrotain",
        ":node_modules/chevrotain-allstar",
        ":node_modules/langium",
        ":node_modules/vscode-jsonrpc",
        ":node_modules/vscode-languageserver-protocol",
        ":node_modules/vscode-languageserver-textdocument",
        ":node_modules/vscode-languageserver-types",
        ":node_modules/vscode-uri",
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
    visibility = ["//charts/bosun/image/frontend:__pkg__"],
)
