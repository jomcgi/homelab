load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

# gazelle:resolve py services.knowledge_graph.app.models //services/knowledge_graph/app:models
# gazelle:resolve py services.knowledge_graph.app.extractors.base //services/knowledge_graph/app/extractors:base
# gazelle:resolve py services.knowledge_graph.app.extractors.html_extractor //services/knowledge_graph/app/extractors:html_extractor
# gazelle:resolve py services.knowledge_graph.app.extractors.feed_extractor //services/knowledge_graph/app/extractors:feed_extractor

py_library(
    name = "extractors",
    srcs = [
        "__init__.py",
        "base.py",
        "feed_extractor.py",
        "html_extractor.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/knowledge_graph/app:models",
        "//services/knowledge_graph/app/extractors:base",
        "//services/knowledge_graph/app/extractors:feed_extractor",
        "//services/knowledge_graph/app/extractors:html_extractor",
        "@pip//feedparser",
        "@pip//httpx",
        "@pip//trafilatura",
    ],
)

py_library(
    name = "base",
    srcs = ["base.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        "//services/knowledge_graph/app:models",
        "@pip//httpx",
    ],
)

py_library(
    name = "html_extractor",
    srcs = ["html_extractor.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":base",
        "//services/knowledge_graph/app:models",
        "@pip//httpx",
        "@pip//lxml_html_clean",
        "@pip//trafilatura",
    ],
)

py_library(
    name = "feed_extractor",
    srcs = ["feed_extractor.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":base",
        "//services/knowledge_graph/app:models",
        "@pip//feedparser",
        "@pip//httpx",
        "@pip//lxml_html_clean",
        "@pip//trafilatura",
    ],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "base_semgrep_test",
    srcs = ["base.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "feed_extractor_semgrep_test",
    srcs = ["feed_extractor.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "html_extractor_semgrep_test",
    srcs = ["html_extractor.py"],
    rules = ["//semgrep_rules:python_rules"],
)
