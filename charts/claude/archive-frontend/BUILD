# Frontend source files for runtime build
filegroup(
    name = "src",
    srcs = glob([
        "src/**/*",
        "public/**/*",
    ]) + [
        "index.html",
        "package.json",
        "postcss.config.js",
        "tailwind.config.js",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
    ],
    visibility = ["//charts/claude/image:__pkg__"],
)
