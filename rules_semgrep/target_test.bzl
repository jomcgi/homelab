"""Bazel test rule for running semgrep against a target's transitive sources."""

load("//rules_semgrep:aspect.bzl", "SemgrepSourcesInfo", "semgrep_source_aspect")

def _semgrep_target_test_impl(ctx):
    info = ctx.attr.target[SemgrepSourcesInfo]
    sources = info.sources.to_list()

    # Collect rule config files
    rule_files = []
    for rule_target in ctx.attr.rules:
        rule_files.extend(rule_target.files.to_list())

    # Build environment variable exports
    env_lines = []
    if ctx.attr.exclude_rules:
        env_lines.append("export SEMGREP_EXCLUDE_RULES=\"{}\"".format(
            ",".join(ctx.attr.exclude_rules),
        ))

    # Upload script path
    upload = ctx.attr._upload[DefaultInfo].files_to_run.executable
    env_lines.append("export UPLOAD_SCRIPT=\"{}\"".format(upload.short_path))

    # Build args for semgrep-test.sh: <rule-files> -- <source-files>
    test_runner = ctx.file._test_runner

    args = [f.short_path for f in rule_files]
    args.append("--")
    args.extend([f.short_path for f in sources])

    # Write launcher script
    launcher = ctx.actions.declare_file(ctx.label.name + ".sh")
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    lines.extend(env_lines)

    if not sources:
        lines.append("echo 'No sources found in target dependency tree'")
        lines.append("exit 0")
    else:
        quoted_args = " ".join(["\"{}\"".format(a) for a in args])
        lines.append("exec \"{}\" {}".format(test_runner.short_path, quoted_args))

    ctx.actions.write(
        output = launcher,
        content = "\n".join(lines) + "\n",
        is_executable = True,
    )

    # Build runfiles — include all files the test needs at runtime
    all_files = [test_runner] + rule_files + sources
    runfiles = ctx.runfiles(files = all_files)

    # Engine runfiles (semgrep-core discovered via find in semgrep-test.sh)
    runfiles = runfiles.merge(ctx.attr._engine[DefaultInfo].default_runfiles)
    runfiles = runfiles.merge(ctx.attr._upload[DefaultInfo].default_runfiles)

    # Pro engine (optional — may be empty filegroup)
    if ctx.attr.pro_engine:
        runfiles = runfiles.merge(ctx.attr.pro_engine[DefaultInfo].default_runfiles)

    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

_semgrep_target_test = rule(
    implementation = _semgrep_target_test_impl,
    test = True,
    attrs = {
        "target": attr.label(
            aspects = [semgrep_source_aspect],
            mandatory = True,
            doc = "Target whose transitive sources will be scanned.",
        ),
        "rules": attr.label_list(
            allow_files = [".yaml"],
            mandatory = True,
            doc = "Semgrep rule config files or filegroups.",
        ),
        "exclude_rules": attr.string_list(
            doc = "Semgrep rule IDs to skip (matched against YAML filename).",
        ),
        "pro_engine": attr.label(
            doc = "Label for semgrep-core-proprietary binary. Enables --pro flag.",
        ),
        "_test_runner": attr.label(
            default = "//rules_semgrep:semgrep-test.sh",
            allow_single_file = True,
        ),
        "_engine": attr.label(default = "//third_party/semgrep:engine"),
        "_upload": attr.label(default = "//tools/semgrep:upload"),
    },
)

def semgrep_target_test(name, target, rules, exclude_rules = [], pro_engine = "//third_party/semgrep_pro:engine", **kwargs):
    """Creates a test that scans a target's transitive sources with semgrep.

    Uses an aspect to walk the target's dependency graph and collect all source
    files from the main repository (excluding external deps). Runs semgrep
    once on the full source closure, enabling meaningful --pro cross-file analysis.

    Args:
        name: Name of the test target.
        target: Label of the target to scan (e.g., a py_venv_binary).
        rules: Semgrep rule config files or filegroups.
        exclude_rules: List of semgrep rule IDs to skip.
        pro_engine: Optional label for semgrep-core-proprietary binary.
        **kwargs: Additional arguments passed to the test rule.
    """
    tags = kwargs.pop("tags", [])
    if "no-sandbox" not in tags:
        tags = tags + ["no-sandbox"]

    _semgrep_target_test(
        name = name,
        target = target,
        rules = rules,
        exclude_rules = exclude_rules,
        pro_engine = pro_engine,
        tags = tags,
        **kwargs
    )
