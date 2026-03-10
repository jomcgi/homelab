"OciImageInfo provider and oci_image_info rule for exposing image metadata to helm_chart."

OciImageInfo = provider(
    doc = "Provides OCI image repository and tag information for use by helm_chart.",
    fields = {
        "repository": "File containing the OCI repository URL (plain text, no trailing newline)",
        "image_tags": "File containing the image tags (one per line; first line is primary tag)",
    },
)

def _oci_image_info_impl(ctx):
    """Write the repository URL to a file and expose OciImageInfo."""
    repo_file = ctx.actions.declare_file(ctx.label.name + ".repository")
    ctx.actions.write(repo_file, ctx.attr.repository)
    return [
        DefaultInfo(files = depset([repo_file])),
        OciImageInfo(
            repository = repo_file,
            image_tags = ctx.file.image_tags,
        ),
    ]

oci_image_info = rule(
    implementation = _oci_image_info_impl,
    attrs = {
        "repository": attr.string(
            mandatory = True,
            doc = "OCI repository URL (e.g. ghcr.io/jomcgi/homelab/my-app)",
        ),
        "image_tags": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "Tags file produced by the CI stamp step (first line is the primary tag)",
        ),
    },
    doc = "Exposes OCI image repository + tag information via OciImageInfo provider.",
)
