load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "agent_orchestrator_mcp",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "image",
    binary = "//services/agent_orchestrator_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/agent-orchestrator-mcp",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)
