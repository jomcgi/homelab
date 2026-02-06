load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

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
    name = "app",
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
        "//services/knowledge_graph/app/embedders",
        "//services/knowledge_graph/app/extractors",
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

py_binary(
    name = "scraper_main",
    srcs = ["scraper_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "//services/knowledge_graph/app/extractors",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pydantic",
        "@pip//pyyaml",
        "@pip//uvicorn",
    ],
)

py_binary(
    name = "embedder_main",
    srcs = ["embedder_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "//services/knowledge_graph/app/embedders",
    ],
)

py_binary(
    name = "mcp_main",
    srcs = ["mcp_main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "//services/knowledge_graph/app/embedders",
        "@pip//fastapi",
        "@pip//pydantic",
        "@pip//uvicorn",
    ],
)
