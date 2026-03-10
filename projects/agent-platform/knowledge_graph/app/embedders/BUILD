load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")

# gazelle:resolve py knowledge_graph.app.embedders.ollama //projects/agent-platform/knowledge_graph/app/embedders:ollama
# gazelle:resolve py knowledge_graph.app.embedders.gemini //projects/agent-platform/knowledge_graph/app/embedders:gemini

py_library(
    name = "embedders",
    srcs = [
        "__init__.py",
        "base.py",
        "gemini.py",
        "ollama.py",
    ],
    imports = ["../../.."],
    visibility = ["//:__subpackages__"],
    deps = [
        "//projects/agent-platform/knowledge_graph/app/embedders:gemini",
        "//projects/agent-platform/knowledge_graph/app/embedders:ollama",
        "@pip//httpx",
    ],
)

py_library(
    name = "base",
    srcs = ["base.py"],
    imports = ["../../.."],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "ollama",
    srcs = ["ollama.py"],
    imports = ["../../.."],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

py_library(
    name = "gemini",
    srcs = ["gemini.py"],
    imports = ["../../.."],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//httpx"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "base_semgrep_test",
    srcs = ["base.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "gemini_semgrep_test",
    srcs = ["gemini.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "ollama_semgrep_test",
    srcs = ["ollama.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
