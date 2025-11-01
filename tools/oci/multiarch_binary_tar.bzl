"multiarch_binary_tar - create tar from architecture-specific binaries"

load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

def multiarch_binary_tar(
        name,
        amd64 = None,
        arm64 = None,
        package_dir = "/usr/local/bin",
        mode = "0755",
        binary_name = None):
    """Create a multiarch tar from architecture-specific binary inputs.

    This helper takes separate binaries for different architectures (e.g., from http_file)
    and packages them into platform-specific tars. The result is a target that apko_image
    can use to layer the correct binary for each platform.

    Args:
        name: Base name for the tar target. Creates internal platform-specific targets.
        amd64: Label for the amd64 binary (e.g., genrule output or http_file)
        arm64: Label for the arm64 binary (e.g., genrule output or http_file)
        package_dir: Directory to place the binary in the image (default: /usr/local/bin)
        mode: File mode as octal string (default: "0755")
        binary_name: Name of the binary in the image (required)

    Creates:
        :{name} - A target providing platform-specific metadata for apko_image

    Example:
        # In your BUILD file
        load("//tools/oci:multiarch_binary_tar.bzl", "multiarch_binary_tar")

        # Genrules to get platform-specific binaries
        genrule(
            name = "ttyd_amd64_file",
            srcs = ["@ttyd_amd64//file"],
            outs = ["bin/amd64/ttyd"],
            cmd = "mkdir -p $$(dirname $@) && cp $< $@",
        )

        genrule(
            name = "ttyd_arm64_file",
            srcs = ["@ttyd_aarch64//file"],
            outs = ["bin/arm64/ttyd"],
            cmd = "mkdir -p $$(dirname $@) && cp $< $@",
        )

        multiarch_binary_tar(
            name = "ttyd_tar",
            amd64 = ":ttyd_amd64_file",
            arm64 = ":ttyd_arm64_file",
            binary_name = "ttyd",
            package_dir = "/usr/local/bin",
        )

        apko_image(
            name = "my_image",
            config = "apko.yaml",
            contents = "@apko_lock//:contents",
            tars = [":ttyd_tar"],
        )
    """
    if not binary_name:
        fail("multiarch_binary_tar: binary_name is required")

    if not amd64 and not arm64:
        fail("multiarch_binary_tar: at least one of amd64 or arm64 must be specified")

    # Create platform-specific tars
    if amd64:
        pkg_tar(
            name = name + "_amd64",
            srcs = [amd64],
            mode = mode,
            package_dir = package_dir,
        )

    if arm64:
        pkg_tar(
            name = name + "_arm64",
            srcs = [arm64],
            mode = mode,
            package_dir = package_dir,
        )

    # Create an alias as the main target
    # apko_image will detect the _amd64/_arm64 suffix pattern
    # and automatically use the correct tar for each platform
    native.alias(
        name = name,
        actual = ":" + name + "_amd64" if amd64 else ":" + name + "_arm64",
        tags = ["multiarch_tar"],
    )
