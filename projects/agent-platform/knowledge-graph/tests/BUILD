load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py projects.agent_platform.knowledge_graph.app.config //projects/agent-platform/knowledge-graph/app:config
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.models //projects/agent-platform/knowledge-graph/app:models
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.chunker //projects/agent-platform/knowledge-graph/app:chunker
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.storage //projects/agent-platform/knowledge-graph/app:storage
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.notifications //projects/agent-platform/knowledge-graph/app:notifications
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.qdrant_client //projects/agent-platform/knowledge-graph/app:qdrant_client
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.extractors.base //projects/agent-platform/knowledge-graph/app/extractors:base
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.extractors.html_extractor //projects/agent-platform/knowledge-graph/app/extractors:html_extractor
# gazelle:resolve py projects.agent_platform.knowledge_graph.app.extractors.feed_extractor //projects/agent-platform/knowledge-graph/app/extractors:feed_extractor

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/agent-platform/knowledge-graph/app:config",
        "//projects/agent-platform/knowledge-graph/app:models",
        "@pip//pytest",
    ],
)

py_test(
    name = "models_test",
    srcs = ["models_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app:models",
    ],
)

py_test(
    name = "chunker_test",
    srcs = ["chunker_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app:chunker",
    ],
)

py_test(
    name = "storage_test",
    srcs = ["storage_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app:models",
        "//projects/agent-platform/knowledge-graph/app:storage",
        "@pip//botocore",
        "@pip//pytest",
    ],
)

py_test(
    name = "extractors_test",
    srcs = ["extractors_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app/extractors:base",
        "//projects/agent-platform/knowledge-graph/app/extractors:feed_extractor",
        "//projects/agent-platform/knowledge-graph/app/extractors:html_extractor",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

py_test(
    name = "notifications_test",
    srcs = ["notifications_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app:models",
        "//projects/agent-platform/knowledge-graph/app:notifications",
        "@pip//pytest",
    ],
)

py_test(
    name = "qdrant_client_test",
    srcs = ["qdrant_client_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app:models",
        "//projects/agent-platform/knowledge-graph/app:qdrant_client",
        "@pip//pytest",
    ],
)

py_test(
    name = "scraper_main_test",
    srcs = ["scraper_main_test.py"],
    deps = [
        ":conftest",
        "//projects/agent-platform/knowledge-graph/app",
        "//projects/agent-platform/knowledge-graph/app:scraper_main",  # keep
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
        "//projects/agent-platform/knowledge-graph/app",
        "//projects/agent-platform/knowledge-graph/app:mcp_main",  # keep
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
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "chunker_test_semgrep_test",
    srcs = ["chunker_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "extractors_test_semgrep_test",
    srcs = ["extractors_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "mcp_main_test_semgrep_test",
    srcs = ["mcp_main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "models_test_semgrep_test",
    srcs = ["models_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "notifications_test_semgrep_test",
    srcs = ["notifications_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "qdrant_client_test_semgrep_test",
    srcs = ["qdrant_client_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "scraper_main_test_semgrep_test",
    srcs = ["scraper_main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "storage_test_semgrep_test",
    srcs = ["storage_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
