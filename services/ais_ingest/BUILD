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
    binary = "//services/ais_ingest:main",
    repository = "ghcr.io/jomcgi/homelab/services/ais_ingest",
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

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
