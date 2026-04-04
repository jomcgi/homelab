# gazelle:exclude chat
# gazelle:exclude app
# gazelle:exclude home
# gazelle:exclude notes
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
        "@pip//opentelemetry_instrumentation_fastapi",
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
    name = "home_scheduler_test",
    srcs = ["home/scheduler_test.py"],
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
