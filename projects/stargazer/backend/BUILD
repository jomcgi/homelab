load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
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
        "//projects/stargazer",
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

py_venv_binary(
    name = "api",
    srcs = ["api.py"],
    main = "api.py",
    visibility = ["//:__subpackages__"],
)

semgrep_target_test(
    name = "api_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":api",
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)
