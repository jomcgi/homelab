"""Bzlmod extension for HuggingFace model downloads.

This extension provides a convenient way to declare HuggingFace models
in MODULE.bazel files.
"""

load("//models/internal:hf_model.bzl", "hf_model")

def _hf_impl(module_ctx):
    """Implementation of the hf module extension."""
    for mod in module_ctx.modules:
        for model in mod.tags.model:
            hf_model(
                name = model.name,
                repo = model.repo_id,
                revision = model.revision,
                files = model.files,
                token = model.token,
            )

_model_tag = tag_class(
    attrs = {
        "name": attr.string(
            mandatory = True,
            doc = "Name for the external repository (used with use_repo)",
        ),
        "repo_id": attr.string(
            mandatory = True,
            doc = "HuggingFace repository ID (e.g., 'sentence-transformers/all-MiniLM-L6-v2')",
        ),
        "revision": attr.string(
            default = "main",
            doc = "Git revision, branch, or tag to download from (default: 'main')",
        ),
        "files": attr.string_dict(
            mandatory = True,
            doc = """Dictionary mapping file paths to their SHA256 checksums.
Keys are file paths in the HuggingFace repo, values are SHA256 checksums.
Example: {"model.safetensors": "abc123...", "config.json": "def456..."}""",
        ),
        "token": attr.string(
            default = "",
            doc = """HuggingFace API token for private repos.
Can be an environment variable name (e.g., 'HF_TOKEN') or a direct token value.
Leave empty for public repositories.""",
        ),
    },
    doc = """Declare a HuggingFace model to download.

Example:
    hf.model(
        name = "all_minilm_l6_v2",
        repo_id = "sentence-transformers/all-MiniLM-L6-v2",
        revision = "main",
        files = {
            "model.safetensors": "abc123...",
            "config.json": "def456...",
        },
    )
""",
)

hf = module_extension(
    implementation = _hf_impl,
    tag_classes = {
        "model": _model_tag,
    },
    doc = """Module extension for downloading HuggingFace models.

This extension allows declaring HuggingFace models in MODULE.bazel files
with SHA256-verified downloads.

Example usage in MODULE.bazel:

    hf = use_extension("//models:extensions.bzl", "hf")

    hf.model(
        name = "all_minilm_l6_v2",
        repo_id = "sentence-transformers/all-MiniLM-L6-v2",
        revision = "main",
        files = {
            "model.safetensors": "abc123...",
            "config.json": "def456...",
            "tokenizer.json": "789xyz...",
        },
    )

    use_repo(hf, "all_minilm_l6_v2")

Then reference in BUILD files:

    some_rule(
        data = ["@all_minilm_l6_v2//:model"],
    )

For private repositories, set HF_TOKEN environment variable:

    hf.model(
        name = "private_model",
        repo_id = "my-org/private-model",
        token = "HF_TOKEN",  # Uses $HF_TOKEN env var
        files = {...},
    )
""",
)
