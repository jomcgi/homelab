# Export files for image packaging
exports_files(
    ["package.json"],
    visibility = ["//charts/claude/image:__pkg__"],
)

filegroup(
    name = "dist",
    srcs = glob(
        ["dist/**/*"],
        allow_empty = True,
    ),
    visibility = ["//charts/claude/image:__pkg__"],
)
