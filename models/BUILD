"""Models package - rules for packaging ML models as OCI images."""

load("@bazel_skylib//:bzl_library.bzl", "bzl_library")
load("//models:defs.bzl", "model_oci_image")

exports_files(
    [
        "defs.bzl",
        "extensions.bzl",
    ],
    visibility = ["//visibility:public"],
)

bzl_library(
    name = "defs",
    srcs = ["defs.bzl"],
    visibility = ["//visibility:public"],
    deps = [
        "//models/internal:gguf",
        "//models/internal:safetensors",
    ],
)

bzl_library(
    name = "extensions",
    srcs = ["extensions.bzl"],
    visibility = ["//visibility:public"],
    deps = ["//models/internal:hf_model"],
)

# =============================================================================
# Proof of Concept Model Targets
# =============================================================================
# These targets demonstrate packaging Qwen 2.5 0.5B models as OCI images.
# The model files are downloaded via the hf bzlmod extension defined in
# MODULE.bazel (see models/extensions.bzl for the extension definition).
#
# To add model definitions to MODULE.bazel:
#
#   hf = use_extension("//models:extensions.bzl", "hf")
#
#   hf.model(
#       name = "qwen2_5_0_5b_gguf",
#       repo_id = "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
#       files = {
#           "qwen2.5-0.5b-instruct-q4_k_m.gguf": "<sha256>",
#       },
#   )
#
#   hf.model(
#       name = "qwen2_5_0_5b_st",
#       repo_id = "Qwen/Qwen2.5-0.5B-Instruct",
#       files = {
#           "model.safetensors": "<sha256>",
#           "config.json": "<sha256>",
#           "tokenizer.json": "<sha256>",
#           "tokenizer_config.json": "<sha256>",
#       },
#   )
#
#   use_repo(hf, "qwen2_5_0_5b_gguf", "qwen2_5_0_5b_st")
# =============================================================================

# GGUF variant - Qwen 2.5 0.5B Instruct quantized model
# Repository auto-generated as ghcr.io/jomcgi/homelab/models/qwen2_5_0_5b_gguf
model_oci_image(
    name = "qwen2_5_0_5b_gguf",
    srcs = ["@qwen2_5_0_5b_gguf//:model_files"],
    format = "gguf",
    model_dir = "/models/qwen2.5-0.5b",
    visibility = ["//visibility:public"],
)

# Safetensors variant - Qwen 2.5 0.5B Instruct full precision
# Repository auto-generated as ghcr.io/jomcgi/homelab/models/qwen2_5_0_5b_st
model_oci_image(
    name = "qwen2_5_0_5b_st",
    config_srcs = [
        "@qwen2_5_0_5b_st//:config_json",
        "@qwen2_5_0_5b_st//:tokenizer_json",
        "@qwen2_5_0_5b_st//:tokenizer_config_json",
    ],
    format = "safetensors",
    model_dir = "/models/qwen2.5-0.5b",
    visibility = ["//visibility:public"],
    weight_srcs = ["@qwen2_5_0_5b_st//:model_safetensors"],
)

# Hermes 4.3 36B AWQ 8-bit - NousResearch reasoning model (~40GB total)
# Repository auto-generated as ghcr.io/jomcgi/homelab/models/hermes_4_3_36b_awq
#
# NOTE: Excluded from CI push_all (tagged "manual") due to large OCI layer blobs.
# Push manually: bazel run //models:hermes_4_3_36b_awq.push
model_oci_image(
    name = "hermes_4_3_36b_awq",
    config_srcs = [
        "@hermes_4_3_36b_awq//:config_json",
        "@hermes_4_3_36b_awq//:generation_config_json",
        "@hermes_4_3_36b_awq//:model_safetensors_index_json",
        "@hermes_4_3_36b_awq//:tokenizer_json",
        "@hermes_4_3_36b_awq//:tokenizer_config_json",
    ],
    format = "safetensors",
    model_dir = "/models/hermes-4.3-36b-awq",
    tags = ["manual"],  # Exclude from //images:push_all
    visibility = ["//visibility:public"],
    weight_srcs = [
        "@hermes_4_3_36b_awq//:model_00001_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00002_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00003_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00004_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00005_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00006_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00007_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00008_of_00009_safetensors",
        "@hermes_4_3_36b_awq//:model_00009_of_00009_safetensors",
    ],
)

# Hermes 4.3 36B IQ4_XS - GGUF quantized model for llama.cpp (~19GB)
# Repository auto-generated as ghcr.io/jomcgi/homelab/models/hermes_4_3_36b_iq4xs
#
# NOTE: Excluded from CI push_all (tagged "manual") due to large OCI layer blobs.
# Push manually: bazel run //models:hermes_4_3_36b_iq4xs.push
model_oci_image(
    name = "hermes_4_3_36b_iq4xs",
    srcs = ["@hermes_4_3_36b_iq4xs//:model_files"],
    format = "gguf",
    model_dir = "/models/hermes-4.3-36b-iq4xs",
    tags = ["manual"],  # Exclude from //images:push_all
    visibility = ["//visibility:public"],
)

# Qwen3 30B A3B AWQ - Production vLLM model (~16GB total)
# Repository auto-generated as ghcr.io/jomcgi/homelab/models/qwen3_30b_a3b_awq
#
# NOTE: Excluded from CI push_all (tagged "manual") due to BuildBuddy cache eviction.
# Large OCI layer blobs (5GB+) exceed cache retention limits, causing CI failures.
# Push manually: bazel run //models:qwen3_30b_a3b_awq.push
model_oci_image(
    name = "qwen3_30b_a3b_awq",
    config_srcs = [
        "@qwen3_30b_a3b_awq//:config_json",
        "@qwen3_30b_a3b_awq//:generation_config_json",
        "@qwen3_30b_a3b_awq//:model_safetensors_index_json",
        "@qwen3_30b_a3b_awq//:tokenizer_json",
        "@qwen3_30b_a3b_awq//:tokenizer_config_json",
    ],
    format = "safetensors",
    model_dir = "/models/qwen3-30b-a3b-awq",
    tags = ["manual"],  # Exclude from //images:push_all
    visibility = ["//visibility:public"],
    weight_srcs = [
        "@qwen3_30b_a3b_awq//:model_00001_of_00004_safetensors",
        "@qwen3_30b_a3b_awq//:model_00002_of_00004_safetensors",
        "@qwen3_30b_a3b_awq//:model_00003_of_00004_safetensors",
        "@qwen3_30b_a3b_awq//:model_00004_of_00004_safetensors",
    ],
)
