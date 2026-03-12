load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "ingest.image": "//projects/ships/ingest:image.info",
        "api.image": "//projects/ships/backend:image.info",
        "frontend.image": "//projects/ships/frontend:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
