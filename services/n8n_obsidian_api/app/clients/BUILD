load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "clients",
    srcs = ["obsidian.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/n8n_obsidian_api/app/models",
        "@pip//httpx",
        "@pip//opentelemetry_api",
    ],
)
