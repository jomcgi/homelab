"multiplatform_tar - create platform-specific tar layers"

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def multiplatform_tar(
        name,
        srcs = None,
        amd64 = None,
        arm64 = None,
        package_dir = "/usr/local/bin",
        mode = "0755",
        remap_to = None,
        strip_prefix = "."):
    """Create platform-specific or platform-agnostic tar layers.

    This is a helper for creating tar layers that contain either:
    1. Platform-specific binaries (use amd64/arm64 parameters)
    2. Platform-agnostic content like node_modules (use srcs parameter)

    Args:
        name: Base name for the tar targets. Creates {name}_amd64 and {name}_arm64 targets.
        srcs: Optional list of labels for platform-agnostic content (e.g., node_modules).
              If specified, creates a single tar used for both platforms.
              Mutually exclusive with amd64/arm64.
        amd64: Label or http_file target for the amd64 file (e.g., "@ttyd_amd64//file").
               Mutually exclusive with srcs.
        arm64: Label or http_file target for the arm64 file (e.g., "@ttyd_aarch64//file").
               Mutually exclusive with srcs.
        package_dir: Directory to place the file in the image (default: /usr/local/bin)
        mode: File mode as octal string (default: "0755")
        remap_to: Optional filename to rename the file to in the image.
                 If not specified, uses the original filename from the label.
                 Useful for renaming "@ttyd_amd64//file" to just "ttyd"
        strip_prefix: Strip prefix for srcs-based tars (default: ".")

    Returns:
        Dict mapping platform names to tar layer targets:
        {"amd64": ":{name}_amd64", "arm64": ":{name}_arm64"}

    Examples:
        # Platform-specific binaries
        ttyd_layers = multiplatform_tar(
            name = "ttyd_layer",
            amd64 = "@ttyd_amd64//file",
            arm64 = "@ttyd_aarch64//file",
            package_dir = "/usr/local/bin",
            remap_to = "ttyd",
        )

        # Platform-agnostic content (node_modules)
        node_layers = multiplatform_tar(
            name = "node_modules_layer",
            srcs = ["//:claude_code"],
            package_dir = "/usr/local/lib",
        )

        apko_image(
            name = "my_image",
            config = "apko.yaml",
            contents = "@apko_lock//:contents",
            multiplatform_tars = [ttyd_layers, node_layers],
        )
    """
    result = {}

    # Validate mutually exclusive parameters
    if srcs and (amd64 or arm64):
        fail("multiplatform_tar: 'srcs' is mutually exclusive with 'amd64' and 'arm64'")

    # Handle platform-agnostic content (same tar for all platforms)
    if srcs:
        pkg_tar(
            name = name,
            srcs = srcs,
            mode = mode,
            package_dir = package_dir,
            strip_prefix = strip_prefix,
        )

        # Use the same tar for both platforms
        result["amd64"] = ":" + name
        result["arm64"] = ":" + name
        return result

    # Handle platform-specific content
    if amd64:
        pkg_tar_kwargs = {
            "name": name + "_amd64",
            "srcs": [amd64],
            "mode": mode,
            "package_dir": package_dir,
        }
        if remap_to:
            # http_file creates files named "downloaded" - remap to desired name
            pkg_tar_kwargs["remap_paths"] = {"external/ttyd_amd64/file/downloaded": remap_to}

        pkg_tar(**pkg_tar_kwargs)
        result["amd64"] = ":" + name + "_amd64"

    if arm64:
        pkg_tar_kwargs = {
            "name": name + "_arm64",
            "srcs": [arm64],
            "mode": mode,
            "package_dir": package_dir,
        }
        if remap_to:
            # http_file creates files named "downloaded" - remap to desired name
            pkg_tar_kwargs["remap_paths"] = {"external/ttyd_aarch64/file/downloaded": remap_to}

        pkg_tar(**pkg_tar_kwargs)
        result["arm64"] = ":" + name + "_arm64"

    return result
