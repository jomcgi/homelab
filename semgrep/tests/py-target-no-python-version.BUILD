load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

# ruleid: py-target-no-python-version
py_binary(
    name = "bad_service",
    srcs = ["main.py"],
    deps = [":lib"],
)

# ok: python_version is specified
py_binary(
    name = "good_service",
    srcs = ["main.py"],
    python_version = "PY3",
    deps = [":lib"],
)

# ok: py_library with python_version
py_library(
    name = "good_lib",
    srcs = ["lib.py"],
    python_version = "PY3",
)
