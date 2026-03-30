# gazelle:ignore
# gazelle:exclude app
# gazelle:exclude todo
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/tools/js:exec_filegroup.bzl", "exec_filegroup")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# Pin the frontend build to the exec (host) platform. The vite output is
# just static HTML/CSS/JS — it's arch-independent — but py3_image's
# platform transitions would otherwise cause aspect_rules_js to select
# wrong-arch native binaries (esbuild, rollup) for the arm64 variant.
exec_filegroup(
    name = "frontend_dist",
    src = "//projects/monolith/frontend:build",
)

py_venv_binary(
    name = "main",
    srcs = glob(
        [
            "app/**/*.py",
            "todo/**/*.py",
        ],
        exclude = ["**/*_test.py"],
    ),
    data = [":frontend_dist"],
    imports = ["."],
    main = "app/main.py",
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
    name = "monolith_backend",
    srcs = glob(
        [
            "app/**/*.py",
            "todo/**/*.py",
        ],
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
    binary = "//projects/monolith:main",
    main = "app/main.py",
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/backend",
)

py_test(
    name = "todo_router_test",
    srcs = ["todo/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
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
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "frontend_test",
    srcs = ["app/frontend_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)
