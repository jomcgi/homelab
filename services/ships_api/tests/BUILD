load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //services/ships_api:ships-api

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
        "//services/ships_api:ships-api",
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
        "//services/ships_api:ships-api",
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
        "//services/ships_api:ships-api",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
