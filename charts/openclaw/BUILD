load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = [
        "//overlays/prod/openclaw-friends:__pkg__",
        "//overlays/prod/openclaw-personal:__pkg__",
    ],
)
