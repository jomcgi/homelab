load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
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
    binary = "//projects/trips/backend:main",
    repository = "ghcr.io/jomcgi/homelab/projects/trips/backend",
)

py_test(
    name = "trips_api_test",
    srcs = ["trips_api_test.py"],
    imports = ["."],
    deps = [
        ":trips_api",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//nats_py",
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
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "trips_api_test_semgrep_test",
    srcs = ["trips_api_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)
