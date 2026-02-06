load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "embedders",
    srcs = [
        "__init__.py",
        "base.py",
        "gemini.py",
        "ollama.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

py_library(
    name = "base",
    srcs = ["base.py"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "ollama",
    srcs = ["ollama.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

py_library(
    name = "gemini",
    srcs = ["gemini.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)
