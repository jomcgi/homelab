"""Bazel test rules for running semgrep scans."""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

def semgrep_test(name, srcs, rules, **kwargs):
    """Creates a cacheable test that runs semgrep against source files.

    Runs semgrep with the given rule configs against the source files and
    fails if any violations are found. Results are cached by Bazel based
    on input file hashes — only re-runs when sources or rules change.

    Args:
        name: Name of the test target
        srcs: Source files to scan (labels)
        rules: Semgrep rule config files or filegroups (labels)
        **kwargs: Additional arguments passed to sh_test
    """
    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = [
                   "$(rootpath //tools/semgrep)",
               ] + ["$(rootpath {})".format(r) for r in rules] +
               ["--"] +
               ["$(rootpath {})".format(s) for s in srcs],
        data = [
            "//tools/semgrep",
        ] + rules + srcs,
        **kwargs
    )

def semgrep_manifest_test(
        name,
        chart,
        chart_files,
        release_name,
        namespace,
        values_files,
        rules = ["//semgrep_rules:kubernetes_rules"],
        **kwargs):
    """Creates a test that renders Helm manifests and scans them with semgrep.

    Combines helm template rendering with semgrep scanning. Fails if either
    rendering fails or semgrep finds violations. Results are cached by Bazel.

    Args:
        name: Name of the test target
        chart: Path to chart directory (e.g., "charts/todo")
        chart_files: Label for chart's filegroup (e.g., "//charts/todo:chart")
        release_name: Helm release name
        namespace: Kubernetes namespace for rendering
        values_files: List of values file labels in order
        rules: Semgrep rule config files (default: kubernetes rules)
        **kwargs: Additional arguments passed to sh_test
    """
    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-manifest-test.sh"],
        args = [
                   "$(rootpath //tools/semgrep)",
                   "$(rootpath @multitool//tools/helm)",
                   release_name,
                   chart,
                   namespace,
               ] + ["$(rootpath {})".format(r) for r in rules] +
               ["--"] +
               ["$(rootpath {})".format(vf) for vf in values_files],
        data = [
            "//tools/semgrep",
            "@multitool//tools/helm",
            chart_files,
        ] + rules + values_files,
        **kwargs
    )
