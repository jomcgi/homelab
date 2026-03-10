load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test", "semgrep_test")

py_library(
    name = "models",
    srcs = ["models.py"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "config",
    srcs = ["config.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//pydantic",
        "@pip//pydantic_settings",
    ],
)

py_library(
    name = "telemetry",
    srcs = ["telemetry.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_sdk",
    ],
)

py_library(
    name = "storage",
    srcs = ["storage.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":models",
        "@pip//boto3",
    ],
)

py_library(
    name = "notifications",
    srcs = ["notifications.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":models",
        "@pip//httpx",
    ],
)

py_library(
    name = "chunker",
    srcs = ["chunker.py"],
    visibility = ["//:__subpackages__"],
    deps = [":models"],
)

py_library(
    name = "qdrant_client",
    srcs = ["qdrant_client.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":models",
        "@pip//httpx",
    ],
)

py_library(
    name = "app",  # keep
    srcs = [
        "__init__.py",
        "chunker.py",
        "config.py",
        "embedder_main.py",
        "mcp_main.py",
        "models.py",
        "notifications.py",
        "qdrant_client.py",
        "scraper_main.py",
        "storage.py",
        "telemetry.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services",
        "@pip//boto3",
        "@pip//botocore",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_sdk",
        "@pip//pydantic",
        "@pip//pydantic_settings",
        "@pip//pyyaml",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "scraper_main",
    srcs = ["scraper_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        ":models",
        ":notifications",
        ":storage",
        ":telemetry",
        "//projects/agent-platform/knowledge-graph/app/extractors",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pydantic",
        "@pip//pyyaml",
    ],
)

py_venv_binary(
    name = "scraper",
    main = "scraper_main.py",
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "embedder_main",
    srcs = ["embedder_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":chunker",
        ":config",
        ":qdrant_client",
        ":storage",
        ":telemetry",
        "//projects/agent-platform/knowledge-graph/app/embedders",
    ],
)

py_venv_binary(
    name = "embedder",
    main = "embedder_main.py",
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "mcp_main",
    srcs = ["mcp_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":config",
        ":qdrant_client",
        ":storage",
        ":telemetry",
        "//projects/agent-platform/knowledge-graph/app/embedders",
        "@pip//fastapi",
        "@pip//pydantic",
    ],
)

py_venv_binary(
    name = "mcp",
    main = "mcp_main.py",
    visibility = ["//:__subpackages__"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_target_test(
    name = "embedder_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":embedder",
)

semgrep_target_test(
    name = "mcp_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":mcp",
)

semgrep_target_test(
    name = "scraper_semgrep_test",
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":scraper",
)

semgrep_test(
    name = "chunker_semgrep_test",
    srcs = ["chunker.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "config_semgrep_test",
    srcs = ["config.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "models_semgrep_test",
    srcs = ["models.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "notifications_semgrep_test",
    srcs = ["notifications.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "qdrant_client_semgrep_test",
    srcs = ["qdrant_client.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "storage_semgrep_test",
    srcs = ["storage.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "telemetry_semgrep_test",
    srcs = ["telemetry.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
