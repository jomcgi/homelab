load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")

py_venv_binary(
    name = "main",
    main = "main.py",
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
    binary = "//services/ships_api:main",
    repository = "ghcr.io/jomcgi/homelab/services/ships_api",
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
