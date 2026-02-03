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
model_oci_image(
    name = "qwen2_5_0_5b_gguf",
    srcs = ["@qwen2_5_0_5b_gguf//:model_files"],
    format = "gguf",
    model_dir = "/models/qwen2.5-0.5b",
    repository = "ghcr.io/joemcginley/models/qwen2.5-0.5b-gguf",
    visibility = ["//visibility:public"],
)

# Safetensors variant - Qwen 2.5 0.5B Instruct full precision
model_oci_image(
    name = "qwen2_5_0_5b_st",
    config_srcs = [
        "@qwen2_5_0_5b_st//:config_json",
        "@qwen2_5_0_5b_st//:tokenizer_json",
        "@qwen2_5_0_5b_st//:tokenizer_config_json",
    ],
    format = "safetensors",
    model_dir = "/models/qwen2.5-0.5b",
    repository = "ghcr.io/joemcginley/models/qwen2.5-0.5b-st",
    visibility = ["//visibility:public"],
    weight_srcs = ["@qwen2_5_0_5b_st//:model_safetensors"],
)
