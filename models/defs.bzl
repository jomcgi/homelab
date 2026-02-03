"""Unified entry point for packaging ML models as OCI images.

This module provides a single `model_oci_image` macro that routes to the
appropriate format-specific implementation based on the model format.
"""

load("//models/internal:gguf.bzl", "gguf_image")
load("//models/internal:safetensors.bzl", "safetensors_image")

def model_oci_image(
        name,
        format,
        repository = None,
        model_dir = "/models",
        **kwargs):
    """Package ML model files as an OCI image.

    This is the unified entry point for creating OCI images containing ML models.
    It routes to the appropriate format-specific implementation based on the
    `format` argument.

    Args:
        name: The name of the image target.
        format: The model format - either "gguf" or "safetensors".
        repository: The container registry repository for pushing
                    (e.g., "ghcr.io/org/models/my-model").
                    Required for push target.
        model_dir: Directory path where models will be mounted in the container.
                   Defaults to "/models".
        **kwargs: Format-specific arguments passed to the underlying rule.

            For "gguf" format:
                srcs: List of GGUF model files to include.
                base: Base image (default: @empty_base).
                visibility: Visibility for generated targets.

            For "safetensors" format:
                weight_srcs: List of .safetensors weight files.
                config_srcs: Optional list of config files (config.json, etc.).
                base: Base image (default: @empty_base).
                visibility: Visibility for generated targets.

    Creates:
        :{name} - The multi-platform oci_image_index target
        :{name}_amd64 - AMD64-specific image
        :{name}_arm64 - ARM64-specific image
        :{name}.push - Target to push image to registry (if repository specified)

    Example:
        load("//models:defs.bzl", "model_oci_image")

        # GGUF model
        model_oci_image(
            name = "llama_gguf",
            format = "gguf",
            srcs = ["@llama_model//:model_files"],
            model_dir = "/models/llama",
            repository = "ghcr.io/myorg/models/llama",
        )

        # Safetensors model
        model_oci_image(
            name = "minilm",
            format = "safetensors",
            weight_srcs = ["@all_minilm//:model_safetensors"],
            config_srcs = [
                "@all_minilm//:config_json",
                "@all_minilm//:tokenizer_json",
            ],
            model_dir = "/models/minilm",
            repository = "ghcr.io/myorg/models/minilm",
        )
    """
    if format == "gguf":
        gguf_image(
            name = name,
            model_dir = model_dir,
            repository = repository,
            **kwargs
        )
    elif format == "safetensors":
        safetensors_image(
            name = name,
            model_dir = model_dir,
            repository = repository,
            **kwargs
        )
    else:
        fail("Unknown model format '{}'. Supported formats: 'gguf', 'safetensors'".format(format))
