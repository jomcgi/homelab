load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")
load("//tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "main",
    main = "main.py",
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
    binary = "//services/trips_api:main",
    repository = "ghcr.io/jomcgi/homelab/services/trips_api",
)

py_test(
    name = "trips_api_test",
    srcs = ["trips_api_test.py"],
    imports = ["."],
    deps = [
        ":trips_api",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_library(
    name = "trips_api",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//uvicorn",
    ],
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
