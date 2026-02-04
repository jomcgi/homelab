"""Tests for OCI image layer validation."""

load("@rules_python//python:defs.bzl", "py_test")

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
    tags = ["manual"],  # Only run on demand since it requires building the model
)
