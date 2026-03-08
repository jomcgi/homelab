"""multitool_tar - Package multitool binaries into per-platform tars.

Reads the multitool lockfile to discover per-platform binary repos and packages
them into tars at a given directory (default /usr/bin/) for each target platform.

This avoids platform transitions entirely by directly referencing the per-platform
repos that rules_multitool already creates (e.g., @multitool.helm.linux_x86_64).
"""

# Map from our platform keys to multitool lockfile os/cpu values.
_PLATFORMS = {
    "linux_amd64": {"os": "linux", "cpu": "x86_64"},
    "linux_arm64": {"os": "linux", "cpu": "arm64"},
    "darwin_arm64": {"os": "macos", "cpu": "arm64"},
}

def _tool_src(hub_name, tool_name, os, cpu):
    """Returns the label for a multitool per-platform binary."""
    return "@{hub}.{tool}.{os}_{cpu}//tools/{tool}:{os}_{cpu}_executable".format(
        hub = hub_name,
        tool = tool_name,
        os = os,
        cpu = cpu,
    )

def multitool_tar(name, tools, package_dir = "/usr/bin", hub_name = "multitool", visibility = None):
    """Package multitool binaries into per-platform tars.

    For each platform (linux_amd64, linux_arm64, darwin_arm64), creates a tar
    containing all requested tool binaries at the specified package_dir.

    Args:
        name: Base name for the generated targets.
        tools: List of tool names from the multitool lockfile (e.g., ["helm", "crane"]).
        package_dir: Directory to place binaries in the tar. Default: /usr/bin
        hub_name: Name of the multitool hub. Default: multitool
        visibility: Visibility of the generated targets.

    Creates:
        :{name}_linux_amd64 - tar with all tool binaries for linux/amd64
        :{name}_linux_arm64 - tar with all tool binaries for linux/arm64
        :{name}_darwin_arm64 - tar with all tool binaries for darwin/arm64
    """
    for platform_key, platform in _PLATFORMS.items():
        os = platform["os"]
        cpu = platform["cpu"]

        srcs = []
        src_labels = []
        for tool_name in tools:
            label = _tool_src(hub_name, tool_name, os, cpu)
            srcs.append(label)
            src_labels.append(tool_name)

        # Build the copy commands: for each tool, copy its binary to the
        # package_dir with the tool name as the filename.
        copy_cmds = []
        for i, tool_name in enumerate(src_labels):
            copy_cmds.append(
                "cp $(location {src}) tmp/{package_dir}/{tool_name}".format(
                    src = srcs[i],
                    package_dir = package_dir.lstrip("/"),
                    tool_name = tool_name,
                ),
            )
            copy_cmds.append(
                "chmod 0755 tmp/{package_dir}/{tool_name}".format(
                    package_dir = package_dir.lstrip("/"),
                    tool_name = tool_name,
                ),
            )

        native.genrule(
            name = name + "_" + platform_key,
            srcs = srcs,
            outs = [name + "_" + platform_key + ".tar"],
            cmd = "\n".join([
                "mkdir -p tmp/{package_dir}".format(package_dir = package_dir.lstrip("/")),
            ] + copy_cmds + [
                "tar -C tmp -cf $@ .",
            ]),
            visibility = visibility,
        )
