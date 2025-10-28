"""Helm render rule for rendering Helm charts."""

def _helm_render_impl(ctx):
    """Implementation of helm_render rule."""
    helm = ctx.toolchains["@rules_multitool//multitool:toolchain"].tool("helm")

    # Collect all value files
    value_files = ctx.files.values

    # Build helm template command
    args = ctx.actions.args()
    args.add("template")
    args.add(ctx.attr.release_name)
    args.add(ctx.file.chart.dirname)
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
        stdout = output,
        mnemonic = "HelmRender",
        progress_message = "Rendering Helm chart %s" % ctx.attr.release_name,
    )

    return [DefaultInfo(files = depset([output]))]

helm_render = rule(
    implementation = _helm_render_impl,
    doc = """Renders a Helm chart to Kubernetes manifests.

    This rule runs `helm template` on a chart with specified values files,
    producing a YAML file containing all Kubernetes manifests.

    Example:
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
    """,
    attrs = {
        "chart": attr.label(
            doc = "The Chart.yaml file of the Helm chart to render",
            allow_single_file = [".yaml", ".yml"],
            mandatory = True,
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
