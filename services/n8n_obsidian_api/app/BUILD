load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "//services/n8n_obsidian_api/app/routers",
        "@pip//fastapi",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//opentelemetry_instrumentation_httpx",
        "@pip//opentelemetry_sdk",
        "@pip//uvicorn",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "config.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/n8n_obsidian_api/app/routers",
        "@pip//fastapi",
        "@pip//opentelemetry_api",
        "@pip//opentelemetry_exporter_otlp_proto_grpc",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//opentelemetry_instrumentation_httpx",
        "@pip//opentelemetry_sdk",
        "@pip//pydantic_settings",
        "@pip//uvicorn",
    ],
)
