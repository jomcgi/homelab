"""node_tar - Package Node.js binary into per-platform tars.

Creates per-platform tars containing the Node.js binary at /usr/bin/node,
sourced from the platform-specific @nodejs_<platform> repos registered
by rules_nodejs in MODULE.bazel.
"""

# Map from our platform keys to rules_nodejs repo suffixes.
_PLATFORMS = {
    "linux_amd64": "linux_amd64",
    "linux_arm64": "linux_arm64",
    "darwin_arm64": "darwin_arm64",
}

def node_tar(name, package_dir = "/usr/bin", visibility = None):
    """Package the Node.js binary into per-platform tars.

    For each platform, creates a tar containing the node binary at package_dir/node.

    Args:
        name: Base name for the generated targets.
        package_dir: Directory to place the binary in the tar. Default: /usr/bin
        visibility: Visibility of the generated targets.

    Creates:
        :{name}_linux_amd64 - tar with node binary for linux/amd64
        :{name}_linux_arm64 - tar with node binary for linux/arm64
        :{name}_darwin_arm64 - tar with node binary for darwin/arm64
    """
    for platform_key, repo_suffix in _PLATFORMS.items():
        node_src = "@nodejs_{suffix}//:node_bin".format(suffix = repo_suffix)

        native.genrule(
            name = name + "_" + platform_key,
            srcs = [node_src],
            outs = [name + "_" + platform_key + ".tar"],
            cmd = "\n".join([
                "mkdir -p tmp/{package_dir}".format(package_dir = package_dir.lstrip("/")),
                "cp $(location {src}) tmp/{package_dir}/node".format(
                    src = node_src,
                    package_dir = package_dir.lstrip("/"),
                ),
                "chmod 0755 tmp/{package_dir}/node".format(
                    package_dir = package_dir.lstrip("/"),
                ),
                "tar -C tmp -cf $@ .",
            ]),
            visibility = visibility,
        )
