load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("@bazel_skylib//:bzl_library.bzl", "bzl_library")
load("//tools/pytest:defs.bzl", "py_test")

"""Tests for OCI image layer validation."""

load(":ghcr_validation.bzl", "ghcr_validation_test")

# =============================================================================
# GHCR Validation Tests - Validate pushed images without downloading blobs
# =============================================================================
# These tests use crane (from Bazel toolchain) to validate images on GHCR.
# No model building or blob downloads required - just metadata checks.
#
# Tagged "ghcr" to run in separate CI job (BuildBuddy "GHCR Validation" action).
# Tagged "external" to exclude from main test suite (non-hermetic, network required).
#
# Fast validation (< 1 second per test) catches GHCR issues immediately.
# Allows validating the 16GB qwen3 model without downloading it!
#
# CI Workflow (main branch only):
#   1. Manual push: bazel run //models:qwen3_30b_a3b_awq.push
#   2. GHCR validation runs and passes
#   3. CI tags validated image with "main" tag
#   4. ArgoCD Image Updater detects digest change on "main" tag
#
# Manual usage:
#   GITHUB_TOKEN=$(gh auth token) bazel run //models/tests:qwen3_30b_a3b_awq_ghcr_test
# =============================================================================

ghcr_validation_test(
    name = "qwen2_5_0_5b_gguf_ghcr_test",
    repository = "jomcgi/homelab/models/qwen2_5_0_5b_gguf",
    tag = "main",
    tags = [
        "external",  # Requires network, excluded from main test suite
        "ghcr",  # GHCR validation test - runs in separate CI job
    ],
)

ghcr_validation_test(
    name = "qwen2_5_0_5b_st_ghcr_test",
    repository = "jomcgi/homelab/models/qwen2_5_0_5b_st",
    tag = "main",
    tags = [
        "external",  # Requires network, excluded from main test suite
        "ghcr",  # GHCR validation test - runs in separate CI job
    ],
)

ghcr_validation_test(
    name = "qwen3_30b_a3b_awq_ghcr_test",
    repository = "jomcgi/homelab/models/qwen3_30b_a3b_awq",
    tag = "main",
    tags = [
        "external",  # Requires network, excluded from main test suite
        "ghcr",  # GHCR validation test - runs in separate CI job
    ],
    # NOTE: This test validates the 16GB model on GHCR without downloading it!
    # Just checks manifest structure via API calls. No disk space needed.
)

# =============================================================================
# Local OCI Validation Tests - Validate locally built images
# =============================================================================
# These tests validate OCI images after building them locally.
# Tagged "manual" because they require building models first.
# =============================================================================

py_test(
    name = "qwen2_5_0_5b_gguf_layers_test",
    srcs = ["validate_oci_layers.py"],
    args = [
        "$(location //models:qwen2_5_0_5b_gguf)",
        "linux/amd64",
        "1",  # Minimum layers: at least 1
    ],
    data = ["//models:qwen2_5_0_5b_gguf"],
    tags = ["manual"],  # Only run on demand since it requires building the model
)

py_test(
    name = "qwen2_5_0_5b_st_layers_test",
    srcs = ["validate_oci_layers.py"],
    args = [
        "$(location //models:qwen2_5_0_5b_st)",
        "linux/amd64",
        "1",  # Minimum layers: at least 1
    ],
    data = ["//models:qwen2_5_0_5b_st"],
    tags = ["manual"],  # Only run on demand since it requires building the model
)

py_test(
    name = "qwen3_30b_a3b_awq_layers_test",
    srcs = ["validate_oci_layers.py"],
    args = [
        "$(location //models:qwen3_30b_a3b_awq)",
        "linux/amd64",
        "1",  # Minimum layers: at least 1
    ],
    data = ["//models:qwen3_30b_a3b_awq"],
    # NOTE: This test requires building the 16GB model. Only run after model is built.
    # The test validates manifest structure, but Bazel will build the model first.
    tags = [
        "large",  # Requires significant disk space
        "manual",  # Don't run in test //...
    ],
)

py_binary(
    name = "validate_oci_layers",
    srcs = ["validate_oci_layers.py"],
    visibility = ["//:__subpackages__"],
)

py_library(
    name = "tests",
    srcs = ["validate_oci_layers.py"],
    visibility = ["//:__subpackages__"],
)

bzl_library(
    name = "ghcr_validation",
    srcs = ["ghcr_validation.bzl"],
    visibility = ["//visibility:public"],
)
