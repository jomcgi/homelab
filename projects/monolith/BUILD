# gazelle:exclude app
# gazelle:exclude schedule
# gazelle:exclude todo
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")
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
            "schedule/**/*.py",
            "todo/**/*.py",
        ],
        exclude = ["**/*_test.py"],
    ),
    data = [":frontend_dist"],
    imports = ["."],  # keep
    main = "app/main.py",
    visibility = ["//:__subpackages__"],
    deps = [":monolith_backend"],  # keep
)

py_library(
    name = "monolith_backend",
    srcs = glob(
        [
            "app/**/*.py",
            "schedule/**/*.py",
            "todo/**/*.py",
        ],
        exclude = ["**/*_test.py"],
    ),
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//icalendar",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//psycopg",
        "@pip//psycopg_binary",
        "@pip//pydantic",
        "@pip//sqlmodel",
        "@pip//tzdata",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//projects/monolith:main",
    env = {
        # py3_image sets PYTHONPATH to the workspace root (_main/) but this
        # project's sibling packages (app/, todo/) need the package directory
        # on the path too, matching the imports = ["."] used by py_venv_binary.
        "PYTHONPATH": "/projects/monolith/main.runfiles/_main:/projects/monolith/main.runfiles/_main/projects/monolith",
    },
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

py_test(
    name = "schedule_service_test",
    srcs = ["schedule/service_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//icalendar",
        "@pip//pytest",
        "@pip//tzdata",
    ],
)

py_test(
    name = "schedule_router_test",
    srcs = ["schedule/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//tzdata",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":main",
)
