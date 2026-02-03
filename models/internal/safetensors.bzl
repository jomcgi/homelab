"""safetensors - Rules for packaging Safetensors models as OCI images.

This module provides rules for packaging Safetensors model files as OCI images
for distribution via container registries like GHCR. Safetensors is a format
designed for efficient and safe storage of tensors, commonly used with
Hugging Face Transformers models.

The key difference from GGUF packaging is the layering strategy:
- Config files (config.json, tokenizer.json, etc.) go in a base layer
- Each .safetensors weight file gets its own layer for efficient caching
- Layer ordering: configs at bottom, weight shards on top
"""

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def safetensors_image(
        name,
        weight_srcs,
        config_srcs = None,
        model_dir = "/models",
        base = "@empty_base",
        repository = None,
        visibility = None,
        tags = None):
    """Package Safetensors model files as an OCI image.

    Creates a multi-platform OCI image containing Safetensors model files with
    an optimized layer structure for efficient caching and partial pulls:
    - Config/tokenizer files in a base layer (rarely changes)
    - Each weight shard in its own layer (allows partial updates)

    Args:
        name: The name of the image target.
        weight_srcs: List of .safetensors weight files to include. Each file will
                     be placed in its own layer for efficient caching. These can be
                     labels pointing to files from hf_model repository rules or
                     local files.
        config_srcs: Optional list of config files (config.json, tokenizer.json,
                     tokenizer_config.json, special_tokens_map.json, etc.) to include
                     in a base layer. If None, no config layer is created.
        model_dir: Directory path where models will be mounted in the container.
                   Defaults to "/models".
        base: The base image to use. Defaults to @empty_base (distroless/static).
        repository: The container registry repository for pushing
                    (e.g., "ghcr.io/org/models/my-model").
                    Required for push target.
        visibility: Visibility for the generated targets.
        tags: Optional list of tags to apply to all generated targets.
              NOTE: The "no-remote-cache" tag is for documentation only and does
              NOT directly control caching. Actual remote cache exclusion is
              enforced via .bazelrc (--modify_execution_info=Tar=+no-remote-cache)
              which applies to ALL Tar actions in CI builds regardless of tags.
              Use this tag to document models with large files (>1GB).

    Creates:
        :{name} - The multi-platform oci_image_index target
        :{name}_amd64 - AMD64-specific image
        :{name}_arm64 - ARM64-specific image
        :{name}.push - Target to push image to registry (if repository specified)

    Example:
        load("//models/internal:safetensors.bzl", "safetensors_image")

        safetensors_image(
            name = "all_minilm_l6_v2",
            config_srcs = [
                "@all_minilm_l6_v2//:config_json",
                "@all_minilm_l6_v2//:tokenizer_json",
                "@all_minilm_l6_v2//:tokenizer_config_json",
            ],
            weight_srcs = [
                "@all_minilm_l6_v2//:model_safetensors",
            ],
            model_dir = "/models/all-MiniLM-L6-v2",
            repository = "ghcr.io/myorg/models/all-minilm-l6-v2",
        )

        # For sharded models (multiple .safetensors files)
        safetensors_image(
            name = "llama_3_8b",
            config_srcs = [
                "@llama_3_8b//:config_json",
                "@llama_3_8b//:tokenizer_json",
                "@llama_3_8b//:generation_config_json",
            ],
            weight_srcs = [
                "@llama_3_8b//:model_00001_of_00004_safetensors",
                "@llama_3_8b//:model_00002_of_00004_safetensors",
                "@llama_3_8b//:model_00003_of_00004_safetensors",
                "@llama_3_8b//:model_00004_of_00004_safetensors",
            ],
            repository = "ghcr.io/myorg/models/llama-3-8b",
        )
    """
    if not weight_srcs:
        fail("weight_srcs cannot be empty - at least one .safetensors file is required")

    # Normalize model_dir to ensure it starts with / and doesn't end with /
    if not model_dir.startswith("/"):
        model_dir = "/" + model_dir
    model_dir = model_dir.rstrip("/")

    # Build tar layers in order: config layer first (bottom), then weight layers (top)
    tar_layers = []

    # Propagate tags to all generated targets
    tags = tags or []

    # Create config layer if config_srcs provided
    if config_srcs:
        pkg_tar(
            name = name + "_config_layer",
            srcs = config_srcs,
            package_dir = model_dir,
            mode = "0644",
            tags = tags,  # Propagate tags to child targets
            visibility = ["//visibility:private"],
        )
        tar_layers.append(name + "_config_layer")

    # Create individual tar layers for each weight file
    # This allows efficient layer caching - unchanged shards won't need re-pushing
    for i, src in enumerate(weight_srcs):
        layer_name = "{}_weight_layer_{}".format(name, i)
        pkg_tar(
            name = layer_name,
            srcs = [src],
            package_dir = model_dir,
            mode = "0644",
            tags = tags,  # Propagate tags to child targets
            visibility = ["//visibility:private"],
        )
        tar_layers.append(layer_name)

    # Create platform-specific images
    # Models are architecture-independent data, so we use the same layers for both
    oci_image(
        name = name + "_amd64",
        base = base + "_linux_amd64",
        tars = tar_layers,
        tags = tags,
        visibility = ["//visibility:private"],
    )

    oci_image(
        name = name + "_arm64",
        base = base + "_linux_arm64_v8",
        tars = tar_layers,
        tags = tags,
        visibility = ["//visibility:private"],
    )

    # Create multi-platform image index
    oci_image_index(
        name = name,
        images = [
            name + "_amd64",
            name + "_arm64",
        ],
        tags = tags,
        visibility = visibility,
    )

    # Auto-generate repository if not specified
    if not repository:
        repository = "ghcr.io/jomcgi/homelab/" + native.package_name() + "/" + name

    # Create stamped tags file for CI builds
    expand_template(
        name = name + "_stamped_tags_ci",
        out = name + "_stamped_ci.tags.txt",
        template = [
            "{STABLE_BRANCH_TAG}",
            "{STABLE_IMAGE_TAG}",
        ],
        stamp_substitutions = {
            "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
            "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
        },
        visibility = ["//visibility:private"],
    )

    # Create stamped tags file for local builds
    expand_template(
        name = name + "_stamped_tags_local",
        out = name + "_stamped_local.tags.txt",
        template = [
            "{STABLE_IMAGE_TAG}",
        ],
        stamp_substitutions = {
            "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
        },
        visibility = ["//visibility:private"],
    )

    oci_push(
        name = name + ".push",
        image = name,
        repository = repository,
        remote_tags = select({
            "//tools/oci:ci_build": name + "_stamped_tags_ci",
            "//conditions:default": name + "_stamped_tags_local",
        }),
        tags = tags,
        visibility = visibility,
    )
