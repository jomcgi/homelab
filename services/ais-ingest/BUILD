load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//uvicorn",
        "@pip//websockets",
    ],
)

py_library(
    name = "ais-ingest",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//uvicorn",
        "@pip//websockets",
    ],
)

py3_image(
    name = "image",
    binary = "//services/ais-ingest:main",
    repository = "ghcr.io/jomcgi/homelab/services/ais-ingest",
)
