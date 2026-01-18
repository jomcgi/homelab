load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//aiosqlite",
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "ships-api",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//aiosqlite",
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//services/ships-api:main",
    repository = "ghcr.io/jomcgi/homelab/services/ships-api",
)
