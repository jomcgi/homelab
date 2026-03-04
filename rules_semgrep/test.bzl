"""Bazel test rules for running semgrep scans."""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

def semgrep_test(name, srcs, rules, exclude_rules = [], pro_engine = None, **kwargs):
    """Creates a cacheable test that runs semgrep against source files.

    Runs semgrep with the given rule configs against the source files and
    fails if any violations are found. Results are cached by Bazel based
    on input file hashes — only re-runs when sources or rules change.

    Args:
        name: Name of the test target
        srcs: Source files to scan (labels)
        rules: Semgrep rule config files or filegroups (labels)
        exclude_rules: List of semgrep rule IDs to skip (e.g., ["no-privileged"])
        pro_engine: Optional label for the semgrep-core-proprietary binary.
            Must resolve to exactly one file. When set, enables --pro flag
            for cross-file analysis.
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"

    # Merge caller tags with no-sandbox: the semgrep pip dependency tree has
    # thousands of files, making darwin-sandbox symlink setup ~100s per test.
    # The scan itself is read-only and safe to run unsandboxed.
    tags = kwargs.pop("tags", [])
    if "no-sandbox" not in tags:
        tags = tags + ["no-sandbox"]

    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
        "//tools/semgrep:upload",
    ] + rules + srcs

    if pro_engine:
        data.append(pro_engine)
        env["SEMGREP_PRO_ENGINE"] = "$(rootpath {})".format(pro_engine)

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = [
                   "$(rootpath //tools/semgrep)",
                   "$(rootpath //tools/semgrep:pysemgrep)",
               ] + ["$(rootpaths {})".format(r) for r in rules] +
               ["--"] +
               ["$(rootpaths {})".format(s) for s in srcs],
        data = data,
        env = env,
        tags = tags,
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
        exclude_rules = [],
        pro_engine = None,
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
        exclude_rules: List of semgrep rule IDs to skip (e.g., ["no-privileged"])
        pro_engine: Optional label for the semgrep-core-proprietary binary.
            Must resolve to exactly one file. When set, enables --pro flag
            for cross-file analysis.
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"

    tags = kwargs.pop("tags", [])
    if "no-sandbox" not in tags:
        tags = tags + ["no-sandbox"]

    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
        "//tools/semgrep:upload",
        "@multitool//tools/helm",
        chart_files,
    ] + rules + values_files

    if pro_engine:
        data.append(pro_engine)
        env["SEMGREP_PRO_ENGINE"] = "$(rootpath {})".format(pro_engine)

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-manifest-test.sh"],
        args = [
                   "$(rootpath //tools/semgrep)",
                   "$(rootpath //tools/semgrep:pysemgrep)",
                   "$(rootpath @multitool//tools/helm)",
                   release_name,
                   chart,
                   namespace,
               ] + ["$(rootpaths {})".format(r) for r in rules] +
               ["--"] +
               ["$(rootpath {})".format(vf) for vf in values_files],
        data = data,
        env = env,
        tags = tags,
        **kwargs
    )
