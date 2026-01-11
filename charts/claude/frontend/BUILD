# CUI Frontend source files for runtime build
# The new CUI frontend is a complete Express server with React frontend
filegroup(
    name = "src",
    srcs = glob([
        "src/**/*",
        "public/**/*",
        "scripts/**/*",
    ]) + [
        "components.json",
        "eslint.config.js",
        "knip.json",
        "LICENSE",
        "package.json",
        "package-lock.json",
        "tailwind.config.js",
        "tsconfig.base.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "tsconfig.web.json",
        "vite.config.mts",
        "vitest.config.ts",
    ],
    visibility = ["//charts/claude/image:__pkg__"],
)
