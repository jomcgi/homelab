load("//bazel/helm:defs.bzl", "helm_chart")

filegroup(
    name = "migrations",
    srcs = glob(["migrations/*.sql", "migrations/atlas.sum"]),
    visibility = ["//projects/monolith:__subpackages__"],
)

helm_chart(
    name = "chart",
    images = {
        "backend.image": "//projects/monolith:image.info",
        "frontend.image": "//projects/monolith/frontend:image.info",
    },
    lint = False,
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
