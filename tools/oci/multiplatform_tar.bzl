"multiplatform_tar - create platform-specific tar layers"

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def multiplatform_tar(
        name,
        amd64 = None,
        arm64 = None,
        package_dir = "/usr/local/bin",
        mode = "0755",
        remap_to = None):
    """Create platform-specific tar layers from platform-specific files.

    This is a helper for creating tar layers that contain platform-specific binaries
    or files that need to be layered on top of multi-platform apko images.

    Args:
        name: Base name for the tar targets. Creates {name}_amd64 and {name}_arm64 targets.
        amd64: Label or http_file target for the amd64 file (e.g., "@ttyd_amd64//file")
        arm64: Label or http_file target for the arm64 file (e.g., "@ttyd_aarch64//file")
        package_dir: Directory to place the file in the image (default: /usr/local/bin)
        mode: File mode as octal string (default: "0755")
        remap_to: Optional filename to rename the file to in the image.
                 If not specified, uses the original filename from the label.
                 Useful for renaming "@ttyd_amd64//file" to just "ttyd"

    Returns:
        Dict mapping platform names to tar layer targets:
        {"amd64": ":{name}_amd64", "arm64": ":{name}_arm64"}

    Example:
        # In your BUILD file
        load("//tools/oci:multiplatform_tar.bzl", "multiplatform_tar")

        ttyd_layers = multiplatform_tar(
            name = "ttyd_layer",
            amd64 = "@ttyd_amd64//file",
            arm64 = "@ttyd_aarch64//file",
            package_dir = "/usr/local/bin",
            remap_to = "ttyd",
        )

        apko_image(
            name = "my_image",
            config = "apko.yaml",
            contents = "@apko_lock//:contents",
            tars_amd64 = [ttyd_layers["amd64"]],
            tars_arm64 = [ttyd_layers["arm64"]],
        )
    """
    result = {}

    if amd64:
        remap_paths = {}
        if remap_to:
            remap_paths[amd64] = remap_to

        pkg_tar(
            name = name + "_amd64",
            srcs = [amd64],
            mode = mode,
            package_dir = package_dir,
            remap_paths = remap_paths,
        )
        result["amd64"] = ":" + name + "_amd64"

    if arm64:
        remap_paths = {}
        if remap_to:
            remap_paths[arm64] = remap_to

        pkg_tar(
            name = name + "_arm64",
            srcs = [arm64],
            mode = mode,
            package_dir = package_dir,
            remap_paths = remap_paths,
        )
        result["arm64"] = ":" + name + "_arm64"

    return result
