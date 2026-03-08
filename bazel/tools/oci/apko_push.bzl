"""Push rule for multi-platform apko images - wraps oci_push with --index flag"""

load("@bazel_skylib//lib:paths.bzl", "paths")

# Transition to target platform (copied from rules_oci push.bzl)
def _transition_to_target_impl(settings, attr):
    return {
        "//command_line_option:extra_execution_platforms": [
            platform
            for platform in settings["//command_line_option:platforms"]
        ],
    }

_transition_to_target = transition(
    implementation = _transition_to_target_impl,
    inputs = ["//command_line_option:platforms"],
    outputs = ["//command_line_option:extra_execution_platforms"],
)

def _rlocationpath(file, workspace_name):
    """Convert file path to rlocation path for runfiles"""
    if file.short_path.startswith("../"):
        return file.short_path[3:]
    return paths.join(workspace_name, file.short_path)

def _apko_push_impl(ctx):
    """Push an apko OCI image (handles multi-platform with --index flag)"""

    # Get crane and jq from toolchains (same as oci_push)
    crane = ctx.attr._crane[0][platform_common.ToolchainInfo]
    jq = ctx.attr._jq[0][platform_common.ToolchainInfo]

    image_dir = ctx.file.image
    if not image_dir.is_directory:
        fail("image must be a directory (from apko_image)")

    # Handle repository
    if ctx.file.repository_file:
        repository_file = ctx.file.repository_file
    elif ctx.attr.repository:
        repository_file = ctx.actions.declare_file(ctx.label.name + ".repository")
        ctx.actions.write(repository_file, ctx.attr.repository)
    else:
        fail("Either repository or repository_file must be specified")

    # Handle tags
    if ctx.file.remote_tags:
        tags_file = ctx.file.remote_tags
    else:
        tags_file = ctx.actions.declare_file(ctx.label.name + ".tags.txt")
        ctx.actions.write(tags_file, "")

    # Create the push script
    push_script = ctx.actions.declare_file(ctx.label.name + ".bash")

    workspace_name = ctx.workspace_name

    ctx.actions.expand_template(
        template = ctx.file._push_template,
        output = push_script,
        is_executable = True,
        substitutions = {
            "{{CRANE}}": _rlocationpath(crane.crane_info.binary, workspace_name),
            "{{JQ}}": _rlocationpath(jq.jqinfo.bin, workspace_name),
            "{{IMAGE_DIR}}": _rlocationpath(image_dir, workspace_name),
            "{{REPOSITORY_FILE}}": _rlocationpath(repository_file, workspace_name),
            "{{TAGS_FILE}}": _rlocationpath(tags_file, workspace_name),
        },
    )

    # Collect runfiles
    runfiles = ctx.runfiles(files = [image_dir, repository_file, tags_file])
    runfiles = runfiles.merge(crane.default.default_runfiles)
    runfiles = runfiles.merge(jq.default.default_runfiles)
    runfiles = runfiles.merge(ctx.attr._runfiles[DefaultInfo].default_runfiles)

    return [DefaultInfo(
        executable = push_script,
        runfiles = runfiles,
    )]

apko_push = rule(
    implementation = _apko_push_impl,
    attrs = {
        "image": attr.label(
            doc = "Label to apko_image output directory",
            mandatory = True,
            allow_single_file = True,
        ),
        "repository": attr.string(
            doc = "Repository URL (e.g., ghcr.io/user/repo)",
        ),
        "repository_file": attr.label(
            doc = "File containing repository URL",
            allow_single_file = True,
        ),
        "remote_tags": attr.label(
            doc = "File with tags (one per line)",
            allow_single_file = True,
        ),
        "_push_template": attr.label(
            default = "//bazel/tools/oci:apko_push.sh.tpl",
            allow_single_file = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
        "_crane": attr.label(
            cfg = _transition_to_target,
            default = "@custom_crane_crane_toolchains//:current_toolchain",
        ),
        "_jq": attr.label(
            cfg = _transition_to_target,
            default = "@jq_toolchains//:resolved_toolchain",
        ),
        "_runfiles": attr.label(
            default = "@bazel_tools//tools/bash/runfiles",
        ),
    },
    executable = True,
)
