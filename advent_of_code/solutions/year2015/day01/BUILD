load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "day01",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

# Data files shared by go/ and python/ tests
exports_files(
    [
        "input.txt",
        "answers.json",
    ],
    visibility = ["//:__subpackages__"],
)
