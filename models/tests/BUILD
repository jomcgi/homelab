"""Tests for OCI image layer validation."""

load("@rules_python//python:defs.bzl", "py_test")
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
# Manual usage:
#   GITHUB_TOKEN=$(gh auth token) bazel run //models/tests:qwen3_30b_a3b_awq_ghcr_test
# =============================================================================

ghcr_validation_test(
    name = "qwen2_5_0_5b_gguf_ghcr_test",
    repository = "jomcgi/homelab/models/qwen2_5_0_5b_gguf",
    tag = "main",
    tags = [
        "ghcr",  # GHCR validation test - runs in separate CI job
        "external",  # Requires network, excluded from main test suite
    ],
)

ghcr_validation_test(
    name = "qwen2_5_0_5b_st_ghcr_test",
    repository = "jomcgi/homelab/models/qwen2_5_0_5b_st",
    tag = "main",
    tags = [
        "ghcr",  # GHCR validation test - runs in separate CI job
        "external",  # Requires network, excluded from main test suite
    ],
)

ghcr_validation_test(
    name = "qwen3_30b_a3b_awq_ghcr_test",
    repository = "jomcgi/homelab/models/qwen3_30b_a3b_awq",
    tag = "main",
    tags = [
        "ghcr",  # GHCR validation test - runs in separate CI job
        "external",  # Requires network, excluded from main test suite
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
    main = "validate_oci_layers.py",
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
    main = "validate_oci_layers.py",
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
    main = "validate_oci_layers.py",
    # NOTE: This test requires building the 16GB model. Only run after model is built.
    # The test validates manifest structure, but Bazel will build the model first.
    tags = [
        "manual",  # Don't run in test //...
        "large",  # Requires significant disk space
    ],
)
