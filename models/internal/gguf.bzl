"""gguf - Rules for packaging GGUF models as OCI images.

This module provides rules for packaging GGUF (GPT-Generated Unified Format) model
files as OCI images for distribution via container registries like GHCR.
"""

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def gguf_image(
        name,
        srcs,
        model_dir = "/models",
        base = "@empty_base",
        repository = None,
        visibility = None,
        tags = None):
    """Package GGUF model files as an OCI image.

    Creates a multi-platform OCI image containing GGUF model files, suitable for
    distribution via container registries. Each source file is placed in a separate
    layer for efficient caching and partial pulls.

    Args:
        name: The name of the image target.
        srcs: List of GGUF model files to include. These can be labels pointing to
              files from hf_model repository rules or local files.
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
        load("//models/internal:gguf.bzl", "gguf_image")

        gguf_image(
            name = "llama_model",
            srcs = ["@llama_3_8b//:model_files"],
            model_dir = "/models/llama",
            repository = "ghcr.io/myorg/models/llama-3-8b",
        )
    """
    if not srcs:
        fail("srcs cannot be empty - at least one model file is required")

    # Normalize model_dir to ensure it starts with / and doesn't end with /
    if not model_dir.startswith("/"):
        model_dir = "/" + model_dir
    model_dir = model_dir.rstrip("/")

    # Propagate tags to all generated targets
    tags = tags or []

    # Create tar layers for model files
    # Using pkg_tar to place files at the correct mount path
    tar_layers = []

    # Create a single tar layer containing all model files
    pkg_tar(
        name = name + "_model_layer",
        srcs = srcs,
        package_dir = model_dir,
        mode = "0644",
        tags = tags,  # Propagate tags to child targets
        visibility = ["//visibility:private"],
    )
    tar_layers.append(name + "_model_layer")

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

def gguf_image_split(
        name,
        srcs,
        model_dir = "/models",
        base = "@empty_base",
        repository = None,
        visibility = None,
        tags = None):
    """Package GGUF model files as an OCI image with one layer per file.

    Similar to gguf_image but creates a separate layer for each source file.
    This is useful for large models where you want maximum layer reuse when
    only some files change, or for split GGUF models where each shard should
    be a separate layer.

    Args:
        name: The name of the image target.
        srcs: List of GGUF model files to include.
        model_dir: Directory path where models will be mounted. Defaults to "/models".
        base: The base image to use. Defaults to @empty_base.
        repository: The container registry repository for pushing.
        visibility: Visibility for the generated targets.

    Creates:
        :{name} - The multi-platform oci_image_index target
        :{name}_amd64 - AMD64-specific image
        :{name}_arm64 - ARM64-specific image
        :{name}.push - Target to push image to registry (if repository specified)

    Example:
        load("//models/internal:gguf.bzl", "gguf_image_split")

        # For split GGUF models
        gguf_image_split(
            name = "llama_70b",
            srcs = [
                "@llama_70b//:model_q4_0_part1_gguf",
                "@llama_70b//:model_q4_0_part2_gguf",
                "@llama_70b//:model_q4_0_part3_gguf",
            ],
            repository = "ghcr.io/myorg/models/llama-70b",
        )
    """
    if not srcs:
        fail("srcs cannot be empty - at least one model file is required")

    # Normalize model_dir
    if not model_dir.startswith("/"):
        model_dir = "/" + model_dir
    model_dir = model_dir.rstrip("/")

    # Propagate tags to all generated targets
    tags = tags or []

    # Create individual tar layers for each source file
    tar_layers = []
    for i, src in enumerate(srcs):
        layer_name = "{}_layer_{}".format(name, i)
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
