"""Helm diff rule for comparing rendered manifests with cluster state."""

def _helm_diff_script_impl(ctx):
    """Implementation of helm_diff_script rule."""

    # Get the rendered manifests
    rendered = ctx.file.rendered

    # Create the diff script
    script = ctx.actions.declare_file(ctx.label.name + ".sh")

    script_content = """#!/usr/bin/env bash
set -euo pipefail

RENDERED="{rendered}"
NAMESPACE="{namespace}"
KUBECTL_CONTEXT="{kubectl_context}"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found in PATH"
    echo "Please install kubectl to use helm diff functionality"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: Cannot connect to Kubernetes cluster"
    echo "Please configure kubectl with cluster access"
    exit 1
fi

# Use specified context if provided
if [[ -n "$KUBECTL_CONTEXT" && "$KUBECTL_CONTEXT" != "current" ]]; then
    CONTEXT_FLAG="--context=$KUBECTL_CONTEXT"
else
    CONTEXT_FLAG=""
fi

echo "Comparing rendered manifests with cluster state..."
echo "Namespace: $NAMESPACE"
echo "Context: $(kubectl config current-context)"
echo ""

# Run kubectl diff
kubectl diff ${CONTEXT_FLAG:+"$CONTEXT_FLAG"} -f "$RENDERED" || true

echo ""
echo "Diff complete. Exit code 0 = no changes, 1 = changes detected"
""".format(
        rendered = rendered.short_path,
        namespace = ctx.attr.namespace,
        kubectl_context = ctx.attr.kubectl_context,
    )

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    return [DefaultInfo(
        files = depset([script]),
        executable = script,
        runfiles = ctx.runfiles(files = [rendered]),
    )]

helm_diff_script = rule(
    implementation = _helm_diff_script_impl,
    doc = """Creates a script to diff rendered Helm manifests against cluster state.

    This rule creates an executable script that uses `kubectl diff` to compare
    the rendered manifests with the current state in the Kubernetes cluster.

    Example:
        helm_diff_script(
            name = "diff",
            rendered = ":render",
            namespace = "n8n",
            kubectl_context = "homelab",
        )

    Run with: bazel run //overlays/prod/n8n:diff
    """,
    attrs = {
        "rendered": attr.label(
            doc = "The rendered manifest file (output of helm_render)",
            allow_single_file = [".yaml"],
            mandatory = True,
        ),
        "namespace": attr.string(
            doc = "The Kubernetes namespace",
            mandatory = True,
        ),
        "kubectl_context": attr.string(
            doc = "The kubectl context to use (default: current context)",
            default = "current",
        ),
    },
    executable = True,
)
