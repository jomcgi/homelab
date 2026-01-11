load("@npm//:vite/package_json.bzl", vite_bin = "bin")
load("@aspect_bazel_lib//lib:copy_to_directory.bzl", "copy_to_directory")

# Build the frontend with Vite using the auto-generated bin rules
vite_bin.vite(
    name = "_vite_build",
    srcs = glob(
        [
            "src/**/*.tsx",
            "src/**/*.css",
            "public/**/*",
        ],
        allow_empty = True,
    ) + [
        "index.html",
        "package.json",
        "postcss.config.js",
        "tailwind.config.js",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
        "//:node_modules/@types/react",
        "//:node_modules/@types/react-dom",
        "//:node_modules/@vitejs/plugin-react",
        "//:node_modules/autoprefixer",
        "//:node_modules/postcss",
        "//:node_modules/react",
        "//:node_modules/react-dom",
        "//:node_modules/tailwindcss",
        "//:node_modules/typescript",
        "//:node_modules/vite",
    ],
    args = [
        "build",
        "--outDir",
        "build_output",
    ],
    chdir = package_name(),
    out_dirs = ["build_output"],
)

# Copy the build output to a platform-independent target
copy_to_directory(
    name = "dist",
    srcs = [":_vite_build"],
    visibility = ["//charts/claude/image:__pkg__"],
)
