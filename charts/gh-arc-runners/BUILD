exports_files(srcs = [
    "Chart.yaml",
    "values.yaml",
])

filegroup(
    name = "all_files",
    srcs = glob(["**/*"]),
    visibility = [
        "//overlays/prod/gh-arc-bazel-runner:__pkg__",
        "//overlays/prod/gh-arc-runners:__pkg__",
    ],
)
