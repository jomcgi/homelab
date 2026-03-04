"""Bazel aspect for collecting transitive source files for semgrep scanning."""

SemgrepSourcesInfo = provider(
    doc = "Carries transitive source files for semgrep scanning.",
    fields = {"sources": "depset of source files from the main repository"},
)

def _semgrep_source_aspect_impl(target, ctx):
    py_sources = []

    # Collect source files from srcs attribute
    if hasattr(ctx.rule.attr, "srcs"):
        for src in ctx.rule.attr.srcs:
            for f in src.files.to_list():
                if not f.short_path.startswith("../"):
                    py_sources.append(f)

    # Collect from main attribute (py_venv_binary)
    if hasattr(ctx.rule.attr, "main"):
        main = ctx.rule.attr.main
        if main:
            main_targets = [main] if type(main) != "list" else main
            for m in main_targets:
                for f in m.files.to_list():
                    if not f.short_path.startswith("../"):
                        py_sources.append(f)

    # Collect transitively from deps
    transitive = []
    if hasattr(ctx.rule.attr, "deps"):
        for dep in ctx.rule.attr.deps:
            if SemgrepSourcesInfo in dep:
                transitive.append(dep[SemgrepSourcesInfo].sources)

    return [SemgrepSourcesInfo(
        sources = depset(py_sources, transitive = transitive),
    )]

semgrep_source_aspect = aspect(
    implementation = _semgrep_source_aspect_impl,
    attr_aspects = ["deps"],
)
