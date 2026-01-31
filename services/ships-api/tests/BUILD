load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py main //services/ships-api:ships-api

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
        "//services/ships-api",
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
        "//services/ships-api",
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
        "//services/ships-api",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
