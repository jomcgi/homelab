load("//bazel/helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/agent_platform/chat_bot:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)
