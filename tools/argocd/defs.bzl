"""Bazel rules for rendering Helm manifests with proper caching."""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

def chart_files(name, visibility):
    """Exports chart files and creates a filegroup of all chart files.

    This macro encapsulates the glob() expression so Gazelle doesn't need to
    parse or merge it. Gazelle only manages the visibility attribute.

    Args:
        name: Name of the filegroup (should be "all_files")
        visibility: List of packages that can reference this filegroup
    """
    native.exports_files([
        "Chart.yaml",
        "values.yaml",
    ])

    native.filegroup(
        name = name,
        srcs = native.glob(["**/*"]),
        visibility = visibility,
    )

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

def helm_lint_test(name, chart_path = None, **kwargs):
    """Creates a test that runs helm lint on a chart.

    The test runs helm lint with --strict mode to catch any issues.

    Args:
        name: Name of the test target
        chart_path: Path to chart directory (default: current package)
        **kwargs: Additional arguments passed to sh_test
    """
    if chart_path == None:
        chart_path = native.package_name()

    # Create an inline script that runs helm lint
    # The script finds the chart in runfiles and lints it
    native.genrule(
        name = name + "_script",
        outs = [name + ".sh"],
        cmd = """cat > $@ << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Find helm binary
HELM="$$1"

# Chart.yaml path - get directory containing it
CHART_YAML="$$2"
CHART_DIR="$$(dirname "$$CHART_YAML")"

if [[ ! -f "$$CHART_YAML" ]]; then
    echo "ERROR: Chart.yaml not found at $$CHART_YAML"
    exit 1
fi

echo "Linting chart: $$CHART_DIR"
"$$HELM" lint "$$CHART_DIR" --strict
echo "PASSED"
EOF
""",
    )

    sh_test(
        name = name,
        srcs = [name + "_script"],
        args = [
            "$(rootpath @multitool//tools/helm)",
            "$(rootpath :Chart.yaml)",
        ],
        data = [
            "@multitool//tools/helm",
            ":Chart.yaml",
            ":values.yaml",
        ] + native.glob(["templates/**"]),
        **kwargs
    )

