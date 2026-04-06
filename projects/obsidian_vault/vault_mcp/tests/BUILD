load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py projects.obsidian_vault.vault_mcp.app.main //projects/obsidian_vault/vault_mcp/app:app

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//pydantic",
        "@pip//pytest",
    ],
)

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pytest_asyncio"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "chunker_test",
    srcs = ["chunker_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
    ],
)

semgrep_test(
    name = "chunker_test_semgrep_test",
    srcs = ["chunker_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "qdrant_client_test",
    srcs = ["qdrant_client_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "qdrant_client_test_semgrep_test",
    srcs = ["qdrant_client_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "embedder_test",
    srcs = ["embedder_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//numpy",
    ],
)

semgrep_test(
    name = "embedder_test_semgrep_test",
    srcs = ["embedder_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "reconciler_test",
    srcs = ["reconciler_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "reconciler_test_semgrep_test",
    srcs = ["reconciler_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "reconciler_extra_test",
    srcs = ["reconciler_extra_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "reconciler_extra_test_semgrep_test",
    srcs = ["reconciler_extra_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "chunker_additional_test",
    srcs = ["chunker_additional_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "chunker_additional_test_semgrep_test",
    srcs = ["chunker_additional_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "qdrant_additional_test",
    srcs = ["qdrant_additional_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//httpx",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "qdrant_additional_test_semgrep_test",
    srcs = ["qdrant_additional_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "embedder_additional_test",
    srcs = ["embedder_additional_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//numpy",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "embedder_additional_test_semgrep_test",
    srcs = ["embedder_additional_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)

py_test(
    name = "main_coverage_test",
    srcs = ["main_coverage_test.py"],
    deps = [
        ":conftest",
        "//projects/obsidian_vault/vault_mcp/app",
        "@pip//pytest",
    ],
)

semgrep_test(
    name = "main_coverage_test_semgrep_test",
    srcs = ["main_coverage_test.py"],
    rules = ["//bazel/semgrep/rules:python_rules"],
)
