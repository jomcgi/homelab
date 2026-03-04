"""Bazel test rule for running semgrep against a target's transitive Python sources."""

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

    pro_file = None
    if ctx.attr.pro_engine:
        pro_files = ctx.attr.pro_engine.files.to_list()
        if pro_files:
            pro_file = pro_files[0]
            env_lines.append("export SEMGREP_PRO_ENGINE=\"{}\"".format(pro_file.short_path))

    # Build args for semgrep-test.sh
    semgrep = ctx.attr._semgrep[DefaultInfo].files_to_run.executable
    pysemgrep = ctx.attr._pysemgrep[DefaultInfo].files_to_run.executable
    test_runner = ctx.file._test_runner

    args = [semgrep.short_path, pysemgrep.short_path]
    args.extend([f.short_path for f in rule_files])
    args.append("--")
    args.extend([f.short_path for f in sources])

    # Write launcher script
    launcher = ctx.actions.declare_file(ctx.label.name + ".sh")
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    lines.extend(env_lines)

    if not sources:
        lines.append("echo 'No Python sources found in target dependency tree'")
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
    if pro_file:
        all_files.append(pro_file)
    runfiles = ctx.runfiles(files = all_files)
    runfiles = runfiles.merge(ctx.attr._semgrep[DefaultInfo].default_runfiles)
    runfiles = runfiles.merge(ctx.attr._pysemgrep[DefaultInfo].default_runfiles)

    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

_semgrep_target_test = rule(
    implementation = _semgrep_target_test_impl,
    test = True,
    attrs = {
        "target": attr.label(
            aspects = [semgrep_source_aspect],
            mandatory = True,
            doc = "Target whose transitive Python sources will be scanned.",
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
            allow_single_file = True,
            doc = "Label for semgrep-core-proprietary binary. Enables --pro flag.",
        ),
        "_test_runner": attr.label(
            default = "//rules_semgrep:semgrep-test.sh",
            allow_single_file = True,
        ),
        "_semgrep": attr.label(default = "//tools/semgrep"),
        "_pysemgrep": attr.label(default = "//tools/semgrep:pysemgrep"),
    },
)

def semgrep_target_test(name, target, rules, exclude_rules = [], pro_engine = None, **kwargs):
    """Creates a test that scans a target's transitive Python sources with semgrep.

    Uses an aspect to walk the target's dependency graph and collect all .py
    files from the main repository (excluding @pip// externals). Runs semgrep
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
