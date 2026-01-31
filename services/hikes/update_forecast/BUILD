load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")
load("//tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "update",
    srcs = ["update.py"],
    data = ["//services/hikes/scrape_walkhighlands:walks.db"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//botocore",
        "@pip//brotli",
        "@pip//pydantic",
        "@pip//python_dateutil",
        "@pip//requests",
    ],
)

py3_image(
    name = "update_image",
    binary = ":update",
)

py_library(
    name = "update_forecast",
    srcs = [
        "__init__.py",
        "update.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//boto3",
        "@pip//botocore",
        "@pip//brotli",
        "@pip//pydantic",
        "@pip//python_dateutil",
        "@pip//requests",
    ],
)

py_test(
    name = "update_test",
    srcs = ["update_test.py"],
    imports = ["."],
    deps = [
        ":update_forecast",
        "@pip//pytest",
        "@pip//requests",
    ],
)
