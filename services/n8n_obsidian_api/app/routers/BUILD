load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "routers",
    srcs = ["notes.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/n8n_obsidian_api/app/clients",
        "//services/n8n_obsidian_api/app/models",
        "//services/n8n_obsidian_api/config",
        "@pip//fastapi",
        "@pip//pydantic",
    ],
)
