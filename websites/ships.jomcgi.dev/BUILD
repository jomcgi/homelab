# Ships frontend website source files for container build
filegroup(
    name = "src",
    srcs = glob(
        [
            "src/**/*",
            "public/**/*",
        ],
        allow_empty = True,
    ) + [
        "index.html",
        "package.json",
        "package-lock.json",
        "vite.config.js",
    ],
    visibility = ["//services/ships-frontend:__pkg__"],
)
