load("//rules_helm:defs.bzl", "helm_chart")

filegroup(
    name = "static_files",
    srcs = glob(["static/**"]),
    visibility = ["//charts/todo/image:__pkg__"],
)

helm_chart(
    name = "chart",
    visibility = ["//overlays/prod/todo:__pkg__"],
)
