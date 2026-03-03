load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py services.knowledge_graph.app.config //services/knowledge_graph/app:config
# gazelle:resolve py services.knowledge_graph.app.models //services/knowledge_graph/app:models
# gazelle:resolve py services.knowledge_graph.app.chunker //services/knowledge_graph/app:chunker
# gazelle:resolve py services.knowledge_graph.app.storage //services/knowledge_graph/app:storage
# gazelle:resolve py services.knowledge_graph.app.notifications //services/knowledge_graph/app:notifications
# gazelle:resolve py services.knowledge_graph.app.qdrant_client //services/knowledge_graph/app:qdrant_client
# gazelle:resolve py services.knowledge_graph.app.extractors.base //services/knowledge_graph/app/extractors:base
# gazelle:resolve py services.knowledge_graph.app.extractors.html_extractor //services/knowledge_graph/app/extractors:html_extractor
# gazelle:resolve py services.knowledge_graph.app.extractors.feed_extractor //services/knowledge_graph/app/extractors:feed_extractor

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/knowledge_graph/app:config",
        "//services/knowledge_graph/app:models",
        "@pip//pytest",
    ],
)

py_test(
    name = "models_test",
    srcs = ["models_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app:models",
    ],
)

py_test(
    name = "chunker_test",
    srcs = ["chunker_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app:chunker",
    ],
)

py_test(
    name = "storage_test",
    srcs = ["storage_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app:models",
        "//services/knowledge_graph/app:storage",
        "@pip//botocore",
        "@pip//pytest",
    ],
)

py_test(
    name = "extractors_test",
    srcs = ["extractors_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app/extractors:base",
        "//services/knowledge_graph/app/extractors:feed_extractor",
        "//services/knowledge_graph/app/extractors:html_extractor",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "notifications_test",
    srcs = ["notifications_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app:models",
        "//services/knowledge_graph/app:notifications",
        "@pip//pytest",
    ],
)

py_test(
    name = "qdrant_client_test",
    srcs = ["qdrant_client_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app:models",
        "//services/knowledge_graph/app:qdrant_client",
        "@pip//pytest",
    ],
)

py_test(
    name = "scraper_main_test",
    srcs = ["scraper_main_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app",
        "//services/knowledge_graph/app:scraper_main",  # keep
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pyyaml",
    ],
)

py_test(
    name = "mcp_main_test",
    srcs = ["mcp_main_test.py"],
    deps = [
        ":conftest",
        "//services/knowledge_graph/app",
        "//services/knowledge_graph/app:mcp_main",  # keep
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "chunker_test_semgrep_test",
    srcs = ["chunker_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "extractors_test_semgrep_test",
    srcs = ["extractors_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "mcp_main_test_semgrep_test",
    srcs = ["mcp_main_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "models_test_semgrep_test",
    srcs = ["models_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "notifications_test_semgrep_test",
    srcs = ["notifications_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "qdrant_client_test_semgrep_test",
    srcs = ["qdrant_client_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "scraper_main_test_semgrep_test",
    srcs = ["scraper_main_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "storage_test_semgrep_test",
    srcs = ["storage_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)
