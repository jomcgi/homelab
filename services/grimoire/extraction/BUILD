load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "tomeslicer",
    srcs = ["tomeslicer.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//google_genai",  # keep
        "@pip//marker_pdf",  # keep
        "@pip//pillow",
        "@pip//pydantic",
        "@pip//typer",
    ],
)

py_library(
    name = "extraction",
    srcs = [
        "__init__.py",
        "tomeslicer.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//pillow",
        "@pip//pydantic",
        "@pip//typer",
    ],
)
