load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

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
