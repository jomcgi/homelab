load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "stargazer",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
    deps = [],
)

# Container image for stargazer with GDAL tools
# Using ubuntu-full variant which includes Python 3.10 with GDAL bindings
# Base includes: gdal_translate, gdalwarp, ogr2ogr, Python GDAL bindings
# Note: osmium-tool not included - need to install via apt or use alternative
py3_image(
    name = "image",
    base = "@gdal_python_base",
    binary = "//projects/stargazer/backend:main",
    env = {
        "GDAL_DATA": "/usr/share/gdal",
        "PROJ_DATA": "/usr/share/proj",
        "DATA_DIR": "/data",
        "OTEL_ENABLED": "false",
    },
    repository = "ghcr.io/jomcgi/homelab/services/stargazer",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
