# gazelle:exclude chat
# gazelle:exclude app
# gazelle:exclude e2e
# gazelle:exclude home
# gazelle:exclude notes
# gazelle:exclude scripts
# gazelle:exclude shared
# gazelle:semgrep_exclude_rules avoid-sqlalchemy-text,tainted-fastapi-http-request-httpx
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_target_test")
load("//bazel/tools/js:exec_filegroup.bzl", "exec_filegroup")
load("//bazel/tools/oci:py3_image.bzl", "py3_image")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# Pin the frontend build to the exec (host) platform. The vite output is
# just static HTML/CSS/JS — it's arch-independent — but py3_image's
# platform transitions would otherwise cause aspect_rules_js to select
# wrong-arch native binaries (esbuild, rollup) for the arm64 variant.
exec_filegroup(
    name = "frontend_dist",
    src = "//projects/monolith/frontend:build",
)

py_venv_binary(
    name = "main",
    srcs = glob(
        # keep
        [
            "app/**/*.py",
            "chat/**/*.py",
            "home/**/*.py",
            "notes/**/*.py",
            "shared/**/*.py",
        ],
        exclude = ["**/*_test.py"],
    ),
    data = [":frontend_dist"],
    imports = ["."],  # keep
    main = "app/main.py",
    visibility = ["//:__subpackages__"],
    deps = [":monolith_backend"],  # keep
)

py_library(
    name = "monolith_backend",
    srcs = glob(
        # keep
        [
            "app/**/*.py",
            "chat/**/*.py",
            "home/**/*.py",
            "notes/**/*.py",
            "shared/**/*.py",
        ],
        exclude = ["**/*_test.py"],
    ),
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//icalendar",
        "@pip//opentelemetry_exporter_otlp_proto_http",
        "@pip//opentelemetry_instrumentation_fastapi",
        "@pip//opentelemetry_sdk",
        "@pip//pgvector",
        "@pip//psycopg",
        "@pip//psycopg_binary",
        "@pip//pydantic",
        "@pip//pydantic_ai_slim",
        "@pip//sqlmodel",
        "@pip//tzdata",
        "@pip//uvicorn",
    ],
)

py3_image(
    name = "image",
    binary = "//projects/monolith:main",
    env = {
        # py3_image sets PYTHONPATH to the workspace root (_main/) but this
        # project's sibling packages (app/, home/) need the package directory
        # on the path too, matching the imports = ["."] used by py_venv_binary.
        "PYTHONPATH": "/projects/monolith/main.runfiles/_main:/projects/monolith/main.runfiles/_main/projects/monolith",
        # The minimal ubuntu base image has no CA certificates; point OpenSSL
        # at certifi's bundle so outbound HTTPS (e.g. Discord gateway) works.
        "SSL_CERT_FILE": "/projects/monolith/main.runfiles/_main/projects/monolith/.main/lib/python3.13/site-packages/certifi/cacert.pem",
    },
    main = "app/main.py",
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/backend",
)

py_test(
    name = "home_router_test",
    srcs = ["home/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "home_startup_test",
    srcs = ["home/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "frontend_test",
    srcs = ["app/frontend_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_service_test",
    srcs = ["shared/service_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//icalendar",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_service_extra_test",
    srcs = ["shared/service_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//icalendar",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_router_test",
    srcs = ["shared/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//tzdata",
    ],
)

py_test(
    name = "notes_router_test",
    srcs = ["notes/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "notes_service_test",
    srcs = ["notes/service_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "home_service_test",
    srcs = ["home/service_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "db_test",
    srcs = ["app/db_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "main_test",
    srcs = ["app/main_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "integration_test",
    size = "medium",
    srcs = ["app/integration_test.py"],
    imports = ["."],
    tags = ["integration"],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "models_test",
    srcs = ["home/models_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_models_test",
    srcs = ["chat/models_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_embedding_test",
    srcs = ["chat/embedding_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_embedding_retry_test",
    srcs = ["chat/embedding_retry_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_embedding_batch_test",
    srcs = ["chat/embedding_batch_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_store_test",
    srcs = ["chat/store_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_web_search_test",
    srcs = ["chat/web_search_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_test",
    srcs = ["chat/bot_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_agent_test",
    srcs = ["chat/agent_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_coverage_test",
    srcs = ["chat/store_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_coverage_test",
    srcs = ["chat/bot_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_web_search_coverage_test",
    srcs = ["chat/web_search_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_embedding_coverage_test",
    srcs = ["chat/embedding_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_agent_deps_test",
    srcs = ["chat/agent_deps_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_agent_coverage_test",
    srcs = ["chat/agent_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "main_coverage_test",
    srcs = ["app/main_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "chat_agent_extra_test",
    srcs = ["chat/agent_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_extra_test",
    srcs = ["chat/bot_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_web_search_extra_test",
    srcs = ["chat/web_search_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_store_extra_test",
    srcs = ["chat/store_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "main_otel_test",
    srcs = ["app/main_otel_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "chat_embedding_extra_test",
    srcs = ["chat/embedding_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_changelog_test",
    srcs = ["chat/changelog_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//httpx",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_changelog_fetch_test",
    srcs = ["chat/changelog_fetch_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_summarizer_test",
    srcs = ["chat/summarizer_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "main_extra_test",
    srcs = ["app/main_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "log_test",
    srcs = ["app/log_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "log_config_test",
    srcs = ["app/log_config_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "main_log_task_test",
    srcs = ["app/main_log_task_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "main_sidecar_test",
    srcs = ["app/main_sidecar_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "store_integrity_test",
    srcs = ["chat/store_integrity_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "bot_self_message_test",
    srcs = ["chat/bot_self_message_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "web_search_headers_test",
    srcs = ["chat/web_search_headers_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_models_summary_test",
    srcs = ["chat/models_summary_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_channel_summary_test",
    srcs = ["chat/store_channel_summary_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_summary_test",
    srcs = ["chat/store_summary_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_vision_errors_test",
    srcs = ["chat/vision_errors_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_summarizer_coverage_test",
    srcs = ["chat/summarizer_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_summarizer_channel_test",
    srcs = ["chat/summarizer_channel_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_exception_test",
    srcs = ["chat/bot_exception_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_error_handling_test",
    srcs = ["chat/bot_error_handling_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_agent_tools_test",
    srcs = ["chat/agent_tools_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_store_attachments_test",
    srcs = ["chat/store_attachments_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_agent_coerce_test",
    srcs = ["chat/agent_coerce_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_store_blob_test",
    srcs = ["chat/store_blob_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_flush_blob_test",
    srcs = ["chat/store_flush_blob_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_save_messages_test",
    srcs = ["chat/store_save_messages_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_embed_text_test",
    srcs = ["chat/store_embed_text_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_bot_backoff_test",
    srcs = ["chat/bot_backoff_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_agent_tool_execution_test",
    srcs = ["chat/agent_tool_execution_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_attachments_test",
    srcs = ["chat/bot_attachments_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_multimodal_test",
    srcs = ["chat/bot_multimodal_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_startup_test",
    srcs = ["chat/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_summarizer_startup_test",
    srcs = ["chat/summarizer_startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_summarizer_prompts_test",
    srcs = ["chat/summarizer_prompts_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_vision_timeout_test",
    srcs = ["chat/vision_timeout_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_web_search_null_results_test",
    srcs = ["chat/web_search_null_results_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_models_persistence_test",
    srcs = ["chat/models_persistence_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_upsert_test",
    srcs = ["chat/store_upsert_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_bulk_test",
    srcs = ["chat/store_bulk_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_models_validation_test",
    srcs = ["chat/models_validation_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "app_main_summary_test",
    srcs = ["app/main_summary_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "app_main_summary_edge_test",
    srcs = ["app/main_summary_edge_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "scripts_red_dashboard_test",
    srcs = ["scripts/generate_red_dashboard_test.py"],
    data = ["scripts/generate-red-dashboard.py"],
    imports = ["."],
    deps = [
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_agent_helper_functions_test",
    srcs = ["chat/agent_helper_functions_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_backfill_test",
    srcs = ["chat/backfill_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_vision_test",
    srcs = ["chat/vision_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_new_coverage_test",
    srcs = ["chat/chat_new_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_web_search_missing_fields_test",
    srcs = ["chat/web_search_missing_fields_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_store_non_integrity_error_test",
    srcs = ["chat/store_non_integrity_error_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlalchemy",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_summarizer_none_id_test",
    srcs = ["chat/summarizer_none_id_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_embedding_null_test",
    srcs = ["chat/embedding_null_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_session_failure_test",
    srcs = ["chat/bot_session_failure_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_thinking_test",
    srcs = ["chat/bot_thinking_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//httpx",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_agent_max_tokens_test",
    srcs = ["chat/agent_max_tokens_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_agent_signpost_test",
    srcs = ["chat/agent_signpost_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_embedding_retryable_test",
    srcs = ["chat/embedding_retryable_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_vision_retryable_test",
    srcs = ["chat/vision_retryable_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_store_null_data_test",
    srcs = ["chat/store_null_data_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_auto_search_test",
    srcs = ["chat/bot_auto_search_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_generate_response_gaps_test",
    srcs = ["chat/bot_generate_response_gaps_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//httpx",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_embedding_connect_timeout_test",
    srcs = ["chat/embedding_connect_timeout_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_agent_web_search_tool_test",
    srcs = ["chat/agent_web_search_tool_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_summary_injection_test",
    srcs = ["chat/bot_summary_injection_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_remaining_gaps_test",
    srcs = ["chat/bot_remaining_gaps_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//httpx",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "e2e_test",
    size = "large",
    timeout = "moderate",
    srcs = [
        "e2e/__init__.py",
        "e2e/conftest.py",
        "e2e/e2e_test.py",
    ],
    data = [
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ],
    imports = ["."],
    tags = ["e2e"],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//psycopg",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
        "@pip//uvicorn",
    ],
)

py_test(
    name = "e2e_playwright_test",
    size = "large",
    timeout = "long",
    srcs = [
        "e2e/__init__.py",
        "e2e/conftest.py",
        "e2e/e2e_playwright_test.py",
    ],
    data = [
        ":frontend_dist",
        "//projects/monolith/chart:migrations",
        "@postgres_test//:postgres",
    ],
    imports = ["."],
    tags = [
        "e2e",
        "manual",
        "playwright",
    ],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//psycopg",
        "@pip//pytest",
        # TODO: add @pip//pytest_playwright once requirements lock is regenerated
        "@pip//sqlmodel",
        "@pip//tzdata",
        "@pip//uvicorn",
    ],
)

py_test(
    name = "chat_router_test",
    srcs = ["chat/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_router_backfill_exception_test",
    srcs = ["chat/router_backfill_exception_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_backfill_flush_test",
    srcs = ["chat/backfill_flush_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_find_user_test",
    srcs = ["chat/store_find_user_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_store_search_model_validate_test",
    srcs = ["chat/store_search_model_validate_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_summarize_oversized_test",
    srcs = ["chat/bot_summarize_oversized_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "chat_bot_thinking_view_callback_test",
    srcs = ["chat/bot_thinking_view_callback_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "scripts_red_dashboard_extra_test",
    srcs = ["scripts/generate_red_dashboard_extra_test.py"],
    data = ["scripts/generate-red-dashboard.py"],
    imports = ["."],
    deps = [
        "@pip//pytest",
    ],
)

py_test(
    name = "scripts_red_dashboard_coverage_test",
    srcs = ["scripts/generate_red_dashboard_coverage_test.py"],
    data = ["scripts/generate-red-dashboard.py"],
    imports = ["."],
    deps = [
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_store_lock_test",
    srcs = ["chat/store_lock_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "chat_bot_reprocess_test",
    srcs = ["chat/bot_reprocess_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)

py_test(
    name = "home_router_archive_test",
    srcs = ["home/router_archive_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "main_lock_sweep_test",
    srcs = ["app/main_lock_sweep_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "main_app_state_test",
    srcs = ["app/main_app_state_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_scheduler_test",
    srcs = ["shared/scheduler_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "shared_scheduler_loop_test",
    srcs = ["shared/scheduler_loop_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "shared_scheduler_tick_missing_job_test",
    srcs = ["shared/scheduler_tick_missing_job_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "shared_startup_test",
    srcs = ["shared/startup_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "home_router_archive_date_format_test",
    srcs = ["home/router_archive_date_format_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "main_log_coverage_test",
    srcs = ["app/main_log_coverage_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_service_calendar_handler_test",
    srcs = ["shared/service_calendar_handler_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//icalendar",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//tzdata",
    ],
)

py_test(
    name = "shared_scheduler_loop_extra_test",
    srcs = ["shared/scheduler_loop_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)

py_test(
    name = "shared_chunker_test",
    srcs = ["shared/chunker_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)

py_test(
    name = "chat_bot_thinking_extra_test",
    srcs = ["chat/bot_thinking_extra_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
    ],
)

py_test(
    name = "scripts_red_dashboard_gaps_test",
    srcs = ["scripts/generate_red_dashboard_gaps_test.py"],
    data = ["scripts/generate-red-dashboard.py"],
    imports = ["."],
    deps = [
        "@pip//pytest",
    ],
)

sh_binary(
    name = "generate-routes",
    srcs = ["generate-routes.sh"],
    visibility = ["//bazel/tools/format:__pkg__"],
)

semgrep_target_test(
    name = "main_semgrep_test",
    exclude_rules = [
        # keep
        "avoid-sqlalchemy-text",
        "tainted-fastapi-http-request-httpx",
    ],
    rules = ["//bazel/semgrep/rules:python_rules"],
    target = ":main",
)
