load("//bazel/helm:defs.bzl", "helm_chart")

filegroup(
    name = "static_files",
    srcs = glob(["static/**"]),
    visibility = ["//charts/todo/image:__pkg__"],
)

helm_chart(
    name = "chart",
    images = {
        "image": "//charts/todo/image:image.info",
    },
    visibility = ["//overlays/prod/todo:__pkg__"],
)
