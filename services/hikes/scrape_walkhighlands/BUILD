# gazelle:semgrep_exclude_rules no-requests
load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "scrape",
    srcs = ["scrape.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":scrape_walkhighlands",
        "@pip//beautifulsoup4",
        "@pip//pydantic",
        "@pip//pydantic_extra_types",
        "@pip//pydantic_sqlite",
        "@pip//requests",
        "@pip//requests_cache",
        "@pip//timelength",
    ],
)

exports_files(["walks.db"])

py_library(
    name = "scrape_walkhighlands",
    srcs = [
        "__init__.py",
        "error_handling.py",
        "scrape.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//beautifulsoup4",
        "@pip//pydantic",
        "@pip//pydantic_extra_types",
        "@pip//pydantic_sqlite",
        "@pip//requests",
        "@pip//requests_cache",
        "@pip//timelength",
    ],
)

py_test(
    name = "error_handling_test",
    srcs = ["error_handling_test.py"],
    imports = ["."],
    deps = [
        ":scrape_walkhighlands",
        "@pip//pytest",
    ],
)

py_test(
    name = "scrape_test",
    srcs = ["scrape_test.py"],
    imports = ["."],
    deps = [
        ":scrape_walkhighlands",
        "@pip//pytest",
        "@pip//requests",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "error_handling_semgrep_test",
    srcs = ["error_handling.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "error_handling_test_semgrep_test",
    srcs = ["error_handling_test.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "scrape_semgrep_test",
    srcs = ["scrape.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "scrape_test_semgrep_test",
    srcs = ["scrape_test.py"],
    exclude_rules = ["no-requests"],
    rules = ["//semgrep_rules:python_rules"],
)
