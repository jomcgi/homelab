"""Helm render rule for rendering Helm charts."""

def _helm_render_impl(ctx):
    """Implementation of helm_render rule."""
    helm = ctx.toolchains["@rules_multitool//multitool:toolchain"].tool("helm")

    # Collect all value files
    value_files = ctx.files.values

    # Determine chart directory
    # Use explicit chart_dir if provided, otherwise derive from Chart.yaml location
    # This defaults to the directory containing Chart.yaml, which is the standard Helm layout
    if ctx.attr.chart_dir:
        chart_dir = ctx.attr.chart_dir
    else:
        chart_dir = ctx.file.chart.dirname

    # Build helm template command
    args = ctx.actions.args()
    args.add("template")
    args.add(ctx.attr.release_name)
    args.add(chart_dir)
    args.add("--namespace", ctx.attr.namespace)

    # Add each values file
    for value_file in value_files:
        args.add("--values", value_file)

    # Add any additional flags
    for flag in ctx.attr.helm_flags:
        args.add(flag)

    # Output file
    output = ctx.actions.declare_file(ctx.label.name + ".yaml")

    # Run helm template
    ctx.actions.run(
        outputs = [output],
        inputs = value_files + [ctx.file.chart],
        executable = helm,
        arguments = [args],
        mnemonic = "HelmRender",
        progress_message = "Rendering Helm chart %s" % ctx.attr.release_name,
    )

    return [DefaultInfo(files = depset([output]))]

helm_render = rule(
    implementation = _helm_render_impl,
    doc = """Renders a Helm chart to Kubernetes manifests.

    This rule runs `helm template` on a chart with specified values files,
    producing a YAML file containing all Kubernetes manifests.

    The chart directory can be specified in two ways:
    1. Implicitly via the 'chart' attribute - the directory containing Chart.yaml is used
    2. Explicitly via the 'chart_dir' attribute - for more control or non-standard layouts

    Standard usage (Chart.yaml at chart root):
        helm_render(
            name = "render",
            chart = "//charts/n8n:Chart.yaml",
            release_name = "n8n",
            namespace = "n8n",
            values = [
                "//charts/n8n:values.yaml",
                "values.yaml",
            ],
        )

    Explicit chart directory (for non-standard layouts):
        helm_render(
            name = "render",
            chart = "//charts/n8n:Chart.yaml",
            chart_dir = "external/some_chart/subdir",
            release_name = "n8n",
            namespace = "n8n",
            values = ["//charts/n8n:values.yaml"],
        )
    """,
    attrs = {
        "chart": attr.label(
            doc = "The Chart.yaml file of the Helm chart to render",
            allow_single_file = [".yaml", ".yml"],
            mandatory = True,
        ),
        "chart_dir": attr.string(
            doc = """Optional: Explicit chart directory path. If not specified, the directory 
            containing the Chart.yaml file (determined by chart attribute) is used automatically.
            This assumes Chart.yaml is located at the root of the chart directory, which is 
            the standard Helm chart layout. Use this attribute only for non-standard layouts 
            where Chart.yaml is not at the chart root, or when you need explicit control over 
            the chart directory path passed to helm template.""",
            mandatory = False,
        ),
        "release_name": attr.string(
            doc = "The name of the Helm release",
            mandatory = True,
        ),
        "namespace": attr.string(
            doc = "The Kubernetes namespace for the release",
            mandatory = True,
        ),
        "values": attr.label_list(
            doc = "List of values files to pass to helm template",
            allow_files = [".yaml", ".yml"],
            default = [],
        ),
        "helm_flags": attr.string_list(
            doc = "Additional flags to pass to helm template",
            default = [],
        ),
    },
    toolchains = ["@rules_multitool//multitool:toolchain"],
)
