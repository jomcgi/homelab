"multiarch_binary_from_http - simplified http_file to multiarch tar"

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def multiarch_binary_from_http(
        name,
        amd64 = None,
        arm64 = None,
        binary_name = None,
        package_dir = "/usr/local/bin",
        mode = "0755"):
    """Create a multiarch tar from http_file downloads.

    This is a convenience wrapper that handles the common pattern of:
    1. Downloading binaries via http_file (in MODULE.bazel)
    2. Renaming them from "downloaded" to the desired binary name
    3. Packaging them into platform-specific tars

    All of this happens in one simple call.

    Args:
        name: Base name for the tar target.
        amd64: Label for the amd64 http_file (e.g., "@ttyd_amd64//file")
        arm64: Label for the arm64 http_file (e.g., "@ttyd_aarch64//file")
        binary_name: Name of the binary in the image (required)
        package_dir: Directory to place the binary in the image (default: /usr/local/bin)
        mode: File mode as octal string (default: "0755")

    Creates:
        :{name}_amd64 - Platform-specific tar for amd64
        :{name}_arm64 - Platform-specific tar for arm64

    Example:
        # In MODULE.bazel, define http_file downloads:
        http_file(
            name = "ttyd_amd64",
            url = "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64",
            sha256 = "...",
        )

        http_file(
            name = "ttyd_aarch64",
            url = "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.aarch64",
            sha256 = "...",
        )

        # In BUILD file:
        load("//tools/oci:multiarch_binary_from_http.bzl", "multiarch_binary_from_http")

        multiarch_binary_from_http(
            name = "ttyd_tar",
            amd64 = "@ttyd_amd64//file",
            arm64 = "@ttyd_aarch64//file",
            binary_name = "ttyd",
        )

        apko_image(
            name = "my_image",
            config = "apko.yaml",
            contents = "@apko_lock//:contents",
            multiarch_tars = [":ttyd_tar"],
        )
    """
    if not binary_name:
        fail("multiarch_binary_from_http: binary_name is required")

    if not amd64 and not arm64:
        fail("multiarch_binary_from_http: at least one of amd64 or arm64 must be specified")

    # Create genrules to rename http_file downloads
    if amd64:
        native.genrule(
            name = name + "_amd64_genrule",
            srcs = [amd64],
            outs = [name + "_amd64_binary"],
            cmd = "cp $< $@",
            executable = True,
        )

        # Package into tar
        pkg_tar(
            name = name + "_amd64",
            srcs = [":" + name + "_amd64_genrule"],
            mode = mode,
            package_dir = package_dir,
            remap_paths = {
                name + "_amd64_binary": binary_name,
            },
        )

    if arm64:
        native.genrule(
            name = name + "_arm64_genrule",
            srcs = [arm64],
            outs = [name + "_arm64_binary"],
            cmd = "cp $< $@",
            executable = True,
        )

        # Package into tar
        pkg_tar(
            name = name + "_arm64",
            srcs = [":" + name + "_arm64_genrule"],
            mode = mode,
            package_dir = package_dir,
            remap_paths = {
                name + "_arm64_binary": binary_name,
            },
        )

    # Create an alias as the main target for apko_image to reference
    native.alias(
        name = name,
        actual = ":" + name + "_amd64" if amd64 else ":" + name + "_arm64",
        tags = ["multiarch_tar"],
    )
