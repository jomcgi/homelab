load("@aspect_rules_ts//ts:defs.bzl", "ts_project")

ts_project(
    name = "src",
    srcs = glob(["src/**/*.ts"]),
    declaration = True,
    out_dir = "dist",
    root_dir = "src",
    tsconfig = "tsconfig.json",
    visibility = ["//charts/claude/image:__pkg__"],
    deps = [
        "//:node_modules/@types/express",
        "//:node_modules/@types/node",
        "//:node_modules/@types/uuid",
        "//:node_modules/@types/ws",
        "//:node_modules/express",
        "//:node_modules/http-proxy-middleware",
        "//:node_modules/uuid",
        "//:node_modules/ws",
    ],
)

# Export package.json for the image
exports_files(
    ["package.json"],
    visibility = ["//charts/claude/image:__pkg__"],
)

# Alias for backward compatibility with image BUILD
alias(
    name = "dist",
    actual = ":src",
    visibility = ["//charts/claude/image:__pkg__"],
)
