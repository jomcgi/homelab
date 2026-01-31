load("//tools/argocd:defs.bzl", "chart_files")

chart_files(
    name = "all_files",
    visibility = ["//overlays/prod/todo:__pkg__"],
)

filegroup(
    name = "static_files",
    srcs = glob(["static/**"]),
    visibility = ["//charts/todo/image:__pkg__"],
)
