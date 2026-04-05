load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //projects/ships/backend:ships-api

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    imports = [".."],
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/ships/backend:ships-api",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "api_test",
    srcs = ["api_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "database_test",
    srcs = ["database_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
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
    name = "api_test_semgrep_test",
    srcs = ["api_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "database_test_semgrep_test",
    srcs = ["database_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "ships_api_test_semgrep_test",
    srcs = ["ships_api_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "service_lifecycle_test",
    srcs = ["service_lifecycle_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
        "@pip//fastapi",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "service_lifecycle_test_semgrep_test",
    srcs = ["service_lifecycle_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "ships_api_test",
    srcs = ["ships_api_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
        "@pip//fastapi",
        "@pip//nats_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",  # keep
    ],
)

semgrep_test(
    name = "vessel_tracking_test_semgrep_test",
    srcs = ["vessel_tracking_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "vessel_tracking_test",
    srcs = ["vessel_tracking_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
        "@pip//fastapi",
        "@pip//pytest",
        "@pip//pytest_asyncio",  # keep
    ],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    imports = [".."],
    deps = [
        ":conftest",
        "//projects/ships/backend:ships-api",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
