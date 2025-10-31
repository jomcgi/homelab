exports_files(srcs = [
    "Chart.yaml",
    "values.yaml",
])

filegroup(
    name = "all_files",
    srcs = glob(["**/*"]),
    visibility = ["//overlays/dev/cloudflare-operator:__pkg__"],
)
