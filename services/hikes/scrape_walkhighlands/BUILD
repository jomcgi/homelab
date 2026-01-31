load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py error_handling //services/hikes/scrape_walkhighlands:scrape_walkhighlands
# gazelle:resolve py scrape //services/hikes/scrape_walkhighlands:scrape_walkhighlands

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
