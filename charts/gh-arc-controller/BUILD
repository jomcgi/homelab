exports_files(srcs = [
    "Chart.yaml",
    "values.yaml",
])

filegroup(
    name = "all_files",
    srcs = glob(["**/*"]),
    visibility = ["//overlays/prod/gh-arc-controller:__pkg__"],
)
