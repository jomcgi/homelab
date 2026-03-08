"""VitePress content declaration rule.

Provides vitepress_filegroup for declaring markdown content that should be
included in the docs site, along with the VitePressContentInfo provider
that carries path mapping metadata for the link rewriter.
"""

VitePressContentInfo = provider(
    doc = "Metadata about a collection of markdown files for inclusion in a VitePress site.",
    fields = {
        "repo_path": "Source package path in the repo (auto-derived from ctx.label.package)",
        "vitepress_path": "Output path in the docs site",
        "files": "Depset of source markdown files",
    },
)

def _vitepress_filegroup_impl(ctx):
    return [
        DefaultInfo(files = depset(ctx.files.srcs)),
        VitePressContentInfo(
            repo_path = ctx.label.package,
            vitepress_path = ctx.attr.vitepress_path,
            files = depset(ctx.files.srcs),
        ),
    ]

vitepress_filegroup = rule(
    implementation = _vitepress_filegroup_impl,
    doc = "Declares markdown files for inclusion in a VitePress documentation site.",
    attrs = {
        "srcs": attr.label_list(
            allow_files = [".md"],
            doc = "Markdown source files to include in the docs site.",
        ),
        "vitepress_path": attr.string(
            mandatory = True,
            doc = "Directory path in the docs site where these files are mounted.",
        ),
    },
)
