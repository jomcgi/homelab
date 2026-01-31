load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //services/trips-api:trips-api

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "trips-api",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//services/trips-api:main",
    repository = "ghcr.io/jomcgi/homelab/services/trips-api",
)

py_test(
    name = "trips_api_test",
    srcs = ["trips_api_test.py"],
    imports = ["."],
    deps = [
        ":trips-api",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
