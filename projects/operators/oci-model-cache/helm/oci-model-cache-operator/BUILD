load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "controllerManager.image": "//projects/operators/oci-model-cache:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
