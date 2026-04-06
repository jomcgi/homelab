load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/stargazer/backend",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

py_test(
    name = "acquisition_test",
    srcs = ["acquisition_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "api_test",
    srcs = ["api_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "config_test",
    srcs = ["config_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "preprocessing_test",
    srcs = ["preprocessing_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pillow",
        "@pip//pytest",
    ],
)

py_test(
    name = "scoring_test",
    srcs = ["scoring_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "spatial_test",
    srcs = ["spatial_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//geopandas",
        "@pip//numpy",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "weather_test",
    srcs = ["weather_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//geopandas",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//shapely",
    ],
)

semgrep_test(
    name = "acquisition_test_semgrep_test",
    srcs = ["acquisition_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "api_test_semgrep_test",
    srcs = ["api_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "config_test_semgrep_test",
    srcs = ["config_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "preprocessing_test_semgrep_test",
    srcs = ["preprocessing_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "scoring_test_semgrep_test",
    srcs = ["scoring_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "spatial_test_semgrep_test",
    srcs = ["spatial_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "weather_test_semgrep_test",
    srcs = ["weather_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "weather_coverage_test",
    srcs = ["weather_coverage_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "preprocessing_coverage_test",
    srcs = ["preprocessing_coverage_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "weather_coverage_test_semgrep_test",
    srcs = ["weather_coverage_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "preprocessing_coverage_test_semgrep_test",
    srcs = ["preprocessing_coverage_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "scoring_additional_test",
    srcs = ["scoring_additional_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "scoring_additional_test_semgrep_test",
    srcs = ["scoring_additional_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "api_additional_test",
    srcs = ["api_additional_test.py"],
    deps = [
        ":conftest",
        "//projects/stargazer/backend",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "api_additional_test_semgrep_test",
    srcs = ["api_additional_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
