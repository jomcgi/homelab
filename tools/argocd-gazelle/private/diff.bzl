"""ArgoCD diff rule using snapshot-based clusters."""

def _argocd_diff_impl(ctx):
    """Implementation of argocd_diff rule."""

    # Create the diff script
    script = ctx.actions.declare_file(ctx.label.name + ".sh")

    # Determine cluster name for snapshot image
    cluster = ctx.attr.cluster if ctx.attr.cluster else "default"
    snapshot_image = ctx.attr.snapshot_image if ctx.attr.snapshot_image else "ghcr.io/jomcgi/argocd-preview:latest"

    script_content = """#!/usr/bin/env bash
set -euo pipefail

APPLICATION_FILE="{application}"
BASE_BRANCH="{base_branch}"
CLUSTER="{cluster}"
SNAPSHOT_IMAGE="{snapshot_image}"

echo "🔍 ArgoCD Diff Preview"
echo "   Application: $APPLICATION_FILE"
echo "   Base: $BASE_BRANCH"
echo "   Cluster: $CLUSTER"
echo "   Snapshot: $SNAPSHOT_IMAGE"
echo ""

# Use the centralized diff script from //tools/argocd:diff
export SNAPSHOT_IMAGE="$SNAPSHOT_IMAGE"

exec "{diff_script}" "$BASE_BRANCH"
""".format(
        application = ctx.file.application.short_path,
        base_branch = ctx.attr.base_branch,
        cluster = cluster,
        snapshot_image = snapshot_image,
        diff_script = ctx.executable._diff_script.short_path,
    )

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    return [DefaultInfo(
        files = depset([script]),
        executable = script,
        runfiles = ctx.runfiles(
            files = [ctx.file.application, ctx.executable._diff_script],
            transitive_files = ctx.attr._diff_script[DefaultInfo].default_runfiles.files,
        ),
    )]

argocd_diff = rule(
    implementation = _argocd_diff_impl,
    doc = """Runs ArgoCD diff preview using snapshot-based cluster.

    This rule creates an executable that uses the ArgoCD snapshot diff tool
    to compare manifests between branches.

    Example:
        argocd_diff(
            name = "diff",
            application = "application.yaml",
            base_branch = "origin/main",
        )

        argocd_diff(
            name = "diff_cluster1",
            application = "application.yaml",
            base_branch = "origin/main",
            cluster = "cluster1",
            snapshot_image = "ghcr.io/jomcgi/argocd-preview:cluster1",
        )

    Run with: bazel run //overlays/prod/n8n:diff
    """,
    attrs = {
        "application": attr.label(
            doc = "The ArgoCD Application manifest file",
            allow_single_file = [".yaml", ".yml"],
            mandatory = True,
        ),
        "base_branch": attr.string(
            doc = "The base branch to compare against (e.g., 'origin/main')",
            default = "origin/main",
        ),
        "cluster": attr.string(
            doc = "Optional: Cluster name for multi-cluster setups",
            default = "",
        ),
        "snapshot_image": attr.string(
            doc = "Optional: Override the snapshot image to use",
            default = "",
        ),
        "_diff_script": attr.label(
            doc = "The centralized ArgoCD diff script",
            default = "//tools/argocd:diff",
            executable = True,
            cfg = "exec",
        ),
    },
    executable = True,
)
