load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //services/ais-ingest:ais-ingest

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//certifi",
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//uvicorn",
        "@pip//websockets",
    ],
)

py_library(
    name = "ais-ingest",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//certifi",
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

py_test(
    name = "ais_ingest_test",
    srcs = ["ais_ingest_test.py"],
    imports = ["."],
    deps = [
        ":ais-ingest",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//nats_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
