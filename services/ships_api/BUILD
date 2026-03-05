load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
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
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//requirements:all.txt"],
    rules = ["//semgrep_rules:python_rules"],
    sca_rules = ["//semgrep_rules:sca_rules"],
    target = ":main",
)
