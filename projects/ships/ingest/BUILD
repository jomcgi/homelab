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
    binary = "//projects/ships/ingest:main",
    repository = "ghcr.io/jomcgi/homelab/projects/ships/ingest",
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
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "ais_ingest_test_semgrep_test",
    srcs = ["ais_ingest_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "ais_parsing_test",
    srcs = ["ais_parsing_test.py"],
    imports = ["."],
    deps = [
        ":ais-ingest",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "ais_parsing_test_semgrep_test",
    srcs = ["ais_parsing_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "ais_edge_cases_test",
    srcs = ["ais_edge_cases_test.py"],
    imports = ["."],
    deps = [
        ":ais-ingest",
        "@pip//nats_py",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "ais_edge_cases_test_semgrep_test",
    srcs = ["ais_edge_cases_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)
