"""Bazel test rules for running semgrep scans via semgrep-core."""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

def semgrep_test(
        name,
        srcs,
        rules,
        exclude_rules = [],
        pro_engine = "//third_party/semgrep_pro:engine",
        **kwargs):
    """Creates a cacheable test that runs semgrep-core against source files.

    Invokes the OCI-vendored semgrep-core binary directly with -rules/-targets
    flags, bypassing the Python pysemgrep wrapper. Results are cached by Bazel
    based on input file hashes — only re-runs when sources or rules change.

    The semgrep-core binary is discovered at runtime via find(1) in the
    runfiles tree, rather than passed as an argument, because the engine
    filegroup may be empty (no GHCR token / empty digest). Empty filegroups
    would cause $(rootpath) to fail at analysis time. The find-based discovery
    gracefully degrades to SKIPPED when the binary is absent.

    Args:
        name: Name of the test target
        srcs: Source files to scan (labels)
        rules: Semgrep rule config files or filegroups (labels)
        exclude_rules: List of semgrep rule IDs to skip (e.g., ["no-privileged"])
        pro_engine: Label for the semgrep-core-proprietary binary filegroup.
            Defaults to the pro engine; set to None to disable pro analysis.
            Empty filegroups (no token/digest) degrade gracefully.
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"

    tags = kwargs.pop("tags", [])

    data = [
        "//third_party/semgrep:engine",
        "//tools/semgrep:upload",
    ] + rules + srcs

    if pro_engine:
        data.append(pro_engine)

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-test.sh"],
        args = ["$(rootpaths {})".format(r) for r in rules] +
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
        pro_engine = "//third_party/semgrep_pro:engine",
        **kwargs):
    """Creates a test that renders Helm manifests and scans them with semgrep-core.

    Combines helm template rendering with semgrep-core scanning. Fails if either
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
        pro_engine: Label for the semgrep-core-proprietary binary filegroup.
            Defaults to the pro engine; set to None to disable pro analysis.
            Empty filegroups (no token/digest) degrade gracefully.
        **kwargs: Additional arguments passed to sh_test
    """
    env = kwargs.pop("env", {})
    if exclude_rules:
        env["SEMGREP_EXCLUDE_RULES"] = ",".join(exclude_rules)
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"

    tags = kwargs.pop("tags", [])

    data = [
        "//third_party/semgrep:engine",
        "//tools/semgrep:upload",
        "@multitool//tools/helm",
        chart_files,
    ] + rules + values_files

    if pro_engine:
        data.append(pro_engine)

    sh_test(
        name = name,
        srcs = ["//rules_semgrep:semgrep-manifest-test.sh"],
        args = [
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
