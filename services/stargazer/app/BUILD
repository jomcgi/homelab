load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "@pip//httpx",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_sdk",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "acquisition.py",
        "api.py",
        "config.py",
        "main.py",
        "preprocessing.py",
        "scoring.py",
        "spatial.py",
        "weather.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//astral",
        "@pip//geopandas",
        "@pip//httpx",
        "@pip//numpy",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_sdk",
        "@pip//osmium",
        "@pip//pillow",
        "@pip//pydantic",
        "@pip//pydantic_settings",
        "@pip//rasterio",
        "@pip//shapely",
    ],
)

py_library(
    name = "config",
    srcs = ["config.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//pydantic",
        "@pip//pydantic_settings",
    ],
)

py_library(
    name = "scoring",
    srcs = ["scoring.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//pydantic",
    ],
)

py_library(
    name = "acquisition",
    srcs = ["acquisition.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        "@pip//httpx",
    ],
)

py_library(
    name = "preprocessing",
    srcs = ["preprocessing.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        "@pip//osmium",
        "@pip//pillow",
    ],
)

py_library(
    name = "spatial",
    srcs = ["spatial.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        "@pip//geopandas",
        "@pip//numpy",
        "@pip//rasterio",
        "@pip//shapely",
    ],
)

py_library(
    name = "weather",
    srcs = ["weather.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        ":scoring",
        "@pip//astral",
        "@pip//geopandas",
        "@pip//httpx",
    ],
)

py_binary(
    name = "api",
    srcs = ["api.py"],
    visibility = ["//:__subpackages__"],
)
