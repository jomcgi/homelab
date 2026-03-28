# gazelle:semgrep_exclude_rules mcp-shell-injection-taint
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")

exports_files(
    ["main.py"],
    visibility = ["//projects/obsidian_vault/image:__pkg__"],
)

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "@pip//fastmcp",
        "@pip//pydantic_settings",
        "@pip//starlette",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "chunker.py",
        "embedder.py",
        "main.py",
        "qdrant_client.py",
        "reconciler.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastembed",
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
        "@pip//starlette",
        "@pip//uvicorn",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    exclude_rules = ["mcp-shell-injection-taint"],
    lockfiles = ["//bazel/requirements:all.txt"],
    rules = ["//bazel/semgrep/rules:python_rules"],
    sca_rules = ["//bazel/semgrep/rules:sca_python_rules"],
    target = ":main",
)

py_library(
    name = "chunker",
    srcs = ["chunker.py"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "qdrant_client",
    srcs = ["qdrant_client.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":chunker",
        "@pip//httpx",
    ],
)

py_library(
    name = "embedder",
    srcs = ["embedder.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastembed",
    ],
)

py_library(
    name = "reconciler",
    srcs = ["reconciler.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":chunker",
        ":embedder",
        ":qdrant_client",
    ],
)
