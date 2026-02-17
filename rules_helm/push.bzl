"""Bazel rules for packaging and pushing Helm charts to OCI registries."""

load("@bazel_skylib//lib:paths.bzl", "paths")

def _rlocationpath(file, workspace_name):
    """Convert file path to rlocation path for runfiles."""
    if file.short_path.startswith("../"):
        return file.short_path[3:]
    return paths.join(workspace_name, file.short_path)

# --- helm_package: build-time rule that produces a .tgz ---

def _helm_package_impl(ctx):
    """Package a Helm chart into a .tgz archive."""
    output = ctx.actions.declare_file(ctx.label.name + ".tgz")

    # Determine the chart directory from the first source file's path.
    # All srcs come from the same chart directory (via glob), so we can
    # derive the chart root from any file's root-relative path.
    first_src = ctx.files.srcs[0]
    chart_dir = first_src.dirname

    # Walk up to find the directory containing Chart.yaml
    # (files may be in subdirectories like templates/)
    for src in ctx.files.srcs:
        if src.basename == "Chart.yaml":
            chart_dir = src.dirname
            break

    ctx.actions.run_shell(
        outputs = [output],
        inputs = ctx.files.srcs,
        tools = [ctx.executable._helm],
        command = """\
set -euo pipefail
"{helm}" package "{chart_dir}" --destination "{out_dir}"
# helm package outputs <name>-<version>.tgz, find and move it
TGZ=$(ls "{out_dir}"/*.tgz)
mv "$TGZ" "{output}"
""".format(
            helm = ctx.executable._helm.path,
            chart_dir = chart_dir,
            out_dir = output.dirname,
            output = output.path,
        ),
        mnemonic = "HelmPackage",
        progress_message = "Packaging Helm chart %s" % ctx.label.name,
    )

    return [DefaultInfo(files = depset([output]))]

helm_package = rule(
    implementation = _helm_package_impl,
    attrs = {
        "srcs": attr.label_list(
            mandatory = True,
            allow_files = True,
            doc = "Chart source files (typically from glob([\"**/*\"]))",
        ),
        "_helm": attr.label(
            default = "@multitool//tools/helm",
            executable = True,
            cfg = "exec",
        ),
    },
    doc = "Packages a Helm chart directory into a .tgz archive.",
)

# --- helm_push: run-time rule that pushes a .tgz to an OCI registry ---

def _helm_push_impl(ctx):
    """Push a packaged Helm chart to an OCI registry."""
    push_script = ctx.actions.declare_file(ctx.label.name + ".bash")

    workspace_name = ctx.workspace_name

    ctx.actions.expand_template(
        template = ctx.file._push_template,
        output = push_script,
        is_executable = True,
        substitutions = {
            "{{HELM}}": _rlocationpath(ctx.executable._helm, workspace_name),
            "{{CHART_TGZ}}": _rlocationpath(ctx.file.chart, workspace_name),
            "{{REPOSITORY}}": ctx.attr.repository,
        },
    )

    runfiles = ctx.runfiles(files = [ctx.file.chart])
    runfiles = runfiles.merge(ctx.attr._helm[DefaultInfo].default_runfiles)
    runfiles = runfiles.merge(ctx.attr._runfiles[DefaultInfo].default_runfiles)

    return [DefaultInfo(
        executable = push_script,
        runfiles = runfiles,
    )]

helm_push = rule(
    implementation = _helm_push_impl,
    attrs = {
        "chart": attr.label(
            mandatory = True,
            allow_single_file = [".tgz"],
            doc = "Packaged Helm chart (.tgz from helm_package)",
        ),
        "repository": attr.string(
            mandatory = True,
            doc = "OCI repository URL (e.g., oci://ghcr.io/user/repo/charts)",
        ),
        "_push_template": attr.label(
            default = "//rules_helm:push.sh.tpl",
            allow_single_file = True,
        ),
        "_helm": attr.label(
            default = "@multitool//tools/helm",
            executable = True,
            cfg = "exec",
        ),
        "_runfiles": attr.label(
            default = "@bazel_tools//tools/bash/runfiles",
        ),
    },
    executable = True,
    doc = "Pushes a packaged Helm chart (.tgz) to an OCI registry.",
)
