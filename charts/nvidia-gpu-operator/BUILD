exports_files(srcs = [
    "Chart.yaml",
    "values.yaml",
])

filegroup(
    name = "all_files",
    srcs = glob(["**/*"]),
    visibility = ["//overlays/cluster-critical/nvidia-gpu-operator:__pkg__"],
)
