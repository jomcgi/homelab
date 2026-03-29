# gazelle:ignore
# gazelle:exclude todo
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_venv_binary(
    name = "main",
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//sqlmodel",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "nexus_backend",
    srcs = glob(
        ["**/*.py"],
        exclude = ["**/*_test.py"],
    ),
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//pydantic",
        "@pip//sqlmodel",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//projects/nexus/backend:main",
    repository = "ghcr.io/jomcgi/homelab/projects/nexus/backend",
)

py_test(
    name = "todo_router_test",
    srcs = ["todo/router_test.py"],
    imports = ["."],
    deps = [
        ":nexus_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "todo_scheduler_test",
    srcs = ["todo/scheduler_test.py"],
    imports = ["."],
    deps = [
        ":nexus_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)
