load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays/dev/bosun:__pkg__"],
)

py_library(
    name = "bosun",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)
