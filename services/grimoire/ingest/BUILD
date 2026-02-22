load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "grimoire-ingest-lib",
    srcs = [
        "__init__.py",
        "chunker.py",
    ],
    visibility = ["//:__subpackages__"],
)

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":grimoire-ingest-lib",
        "@pip//boto3",
        "@pip//botocore",
        "@pip//google_genai",
        "@pip//nats_py",
        "@pip//pymupdf",
        "@pip//pymupdf4llm",
    ],
)

py3_image(
    name = "image",
    binary = ":main",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-ingest",
)
