"""go_tar - Package Go SDK into per-platform tars.

Downloads the official Go SDK tarballs and repackages them at /usr/local/go/
with a symlink at /usr/bin/go for PATH discovery.

Uses http_file repos registered in MODULE.bazel (go_sdk_linux_amd64, etc.)
that contain the raw .tar.gz from go.dev/dl/.
"""

# Map from our platform keys to the http_file repo suffixes.
_PLATFORMS = {
    "linux_amd64": "linux_amd64",
    "linux_arm64": "linux_arm64",
    "darwin_arm64": "darwin_arm64",
}

def go_tar(name, version, visibility = None):
    """Package Go SDK tarballs into per-platform OCI layer tars.

    For each platform, creates a tar containing the full Go SDK at /usr/local/go/
    with a symlink at /usr/bin/go.

    Args:
        name: Base name for the generated targets.
        version: Go version string (e.g., "1.24.1") — used only in target naming docs.
        visibility: Visibility of the generated targets.

    Requires http_file repos named @go_sdk_{platform} in MODULE.bazel.

    Creates:
        :{name}_linux_amd64 - tar with Go SDK for linux/amd64
        :{name}_linux_arm64 - tar with Go SDK for linux/arm64
        :{name}_darwin_arm64 - tar with Go SDK for darwin/arm64
    """
    for platform_key, repo_suffix in _PLATFORMS.items():
        sdk_src = "@go_sdk_{suffix}//file".format(suffix = repo_suffix)

        native.genrule(
            name = name + "_" + platform_key,
            srcs = [sdk_src],
            outs = [name + "_" + platform_key + ".tar"],
            cmd = "\n".join([
                "set -e",
                "WORK=$$(mktemp -d)",
                "mkdir -p $$WORK/usr/local",
                # Extract go/ -> usr/local/go/
                "tar xzf $< -C $$WORK/usr/local",
                # Symlink for PATH discovery
                "mkdir -p $$WORK/usr/bin",
                "ln -s ../local/go/bin/go $$WORK/usr/bin/go",
                "tar -C $$WORK -cf $@ .",
                "rm -rf $$WORK",
            ]),
            visibility = visibility,
        )
