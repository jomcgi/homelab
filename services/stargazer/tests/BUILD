load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/stargazer/app",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

py_test(
    name = "acquisition_test",
    srcs = ["acquisition_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "api_test",
    srcs = ["api_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//pytest",
    ],
)

py_test(
    name = "config_test",
    srcs = ["config_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//pytest",
    ],
)

py_test(
    name = "preprocessing_test",
    srcs = ["preprocessing_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//pillow",
        "@pip//pytest",
    ],
)

py_test(
    name = "scoring_test",
    srcs = ["scoring_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//pytest",
    ],
)

py_test(
    name = "spatial_test",
    srcs = ["spatial_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//geopandas",
        "@pip//numpy",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

py_test(
    name = "weather_test",
    srcs = ["weather_test.py"],
    deps = [
        ":conftest",
        "//services/stargazer/app",
        "@pip//geopandas",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

semgrep_test(
    name = "semgrep_test",
    srcs = glob(["*.py"]),
    rules = ["//semgrep_rules:python_rules"],
)
