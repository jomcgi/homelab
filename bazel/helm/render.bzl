"""Bazel rule for rendering Helm manifests with proper caching."""

def _helm_render_impl(ctx):
    """Implementation of helm_render rule.

    This rule properly declares outputs so Bazel can cache them.
    Bazel will only re-render when inputs (chart, values, helm binary) change.
    """
    output = ctx.actions.declare_file(ctx.attr.output_filename)

    # Build helm template command
    helm_cmd = [
        ctx.executable._helm.path,
        "template",
        ctx.attr.release_name,
        ctx.file.chart.path,
        "--namespace",
        ctx.attr.namespace,
    ]

    # Add values files
    for values_file in ctx.files.values_files:
        helm_cmd.extend(["--values", values_file.path])

    # Render manifests
    ctx.actions.run_shell(
        outputs = [output],
        inputs = depset(
            direct = [ctx.file.chart] + ctx.files.values_files + ctx.files._chart_deps,
            transitive = [ctx.attr._helm[DefaultInfo].default_runfiles.files],
        ),
        tools = [ctx.executable._helm],
        command = "{} > {}".format(" ".join(helm_cmd), output.path),
        mnemonic = "HelmRender",
        progress_message = "Rendering Helm manifests for %s" % ctx.attr.release_name,
    )

    return [DefaultInfo(files = depset([output]))]

helm_render = rule(
    implementation = _helm_render_impl,
    attrs = {
        "chart": attr.label(
            mandatory = True,
            allow_single_file = True,
            doc = "Chart.yaml file for the Helm chart",
        ),
        "release_name": attr.string(
            mandatory = True,
            doc = "Helm release name",
        ),
        "namespace": attr.string(
            default = "default",
            doc = "Kubernetes namespace",
        ),
        "values_files": attr.label_list(
            allow_files = [".yaml", ".yml"],
            doc = "List of values files to merge (in order)",
        ),
        "output_filename": attr.string(
            mandatory = True,
            doc = "Output filename (relative to this package)",
        ),
        "_helm": attr.label(
            default = "@multitool//tools/helm",
            executable = True,
            cfg = "exec",
        ),
        "_chart_deps": attr.label_list(
            default = [],
            allow_files = True,
            doc = "Additional chart dependencies (templates, etc.)",
        ),
    },
    doc = """Renders Helm manifests with proper Bazel caching.

    This rule declares outputs so Bazel can cache them based on input hashes.
    Only re-renders when chart files, values files, or helm binary change.

    Example:
        helm_render(
            name = "manifests",
            chart = "//charts/myapp:Chart.yaml",
            release_name = "myapp",
            namespace = "production",
            values_files = [
                "//charts/myapp:values.yaml",
                "values.yaml",
            ],
            output_filename = "manifests/all.yaml",
        )
    """,
)
