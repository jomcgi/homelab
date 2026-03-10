"""VitePress site macro — assembles content, rewrites links, builds, and deploys.

Provides vitepress_site, a high-level macro that wires together content
assembly, link rewriting, VitePress building, and Cloudflare Pages deployment.
"""

load("@aspect_rules_js//js:defs.bzl", "js_run_binary")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("//bazel/tools/js:vite_build.bzl", "vite_build")
load("//bazel/vitepress:defs.bzl", "VitePressContentInfo")
load("//bazel/wrangler:defs.bzl", "wrangler_pages")

def _assemble_impl(ctx):
    """Collect files from vitepress_filegroup deps into a directory tree."""
    output_dir = ctx.actions.declare_directory(ctx.attr.name)

    # Build shell commands to copy files into the output directory
    commands = ["#!/bin/bash", "set -euo pipefail", ""]

    for dep in ctx.attr.content:
        info = dep[VitePressContentInfo]
        vitepress_path = info.vitepress_path
        repo_path = info.repo_path

        for f in info.files.to_list():
            # Compute the relative path within the source package
            if repo_path:
                rel = f.short_path
                if rel.startswith(repo_path + "/"):
                    rel = rel[len(repo_path) + 1:]
            else:
                rel = f.short_path

            dest = paths.join(output_dir.path, vitepress_path, rel)
            commands.append("mkdir -p \"$(dirname '%s')\"" % dest)
            commands.append("cp '%s' '%s'" % (f.path, dest))

    script = ctx.actions.declare_file(ctx.attr.name + "_assemble.sh")
    ctx.actions.write(script, "\n".join(commands), is_executable = True)

    inputs = []
    for dep in ctx.attr.content:
        info = dep[VitePressContentInfo]
        inputs.extend(info.files.to_list())

    ctx.actions.run(
        executable = script,
        inputs = inputs,
        outputs = [output_dir],
        mnemonic = "VitePressAssemble",
        progress_message = "Assembling VitePress content into %s" % output_dir.short_path,
    )

    return [DefaultInfo(files = depset([output_dir]))]

_assemble = rule(
    implementation = _assemble_impl,
    attrs = {
        "content": attr.label_list(
            providers = [VitePressContentInfo],
            doc = "vitepress_filegroup targets to assemble.",
        ),
    },
)

def _path_map_impl(ctx):
    """Generate a JSON path map from VitePressContentInfo providers."""
    output = ctx.actions.declare_file(ctx.attr.name + ".json")

    path_map = {}
    for dep in ctx.attr.content:
        info = dep[VitePressContentInfo]
        path_map[info.repo_path] = info.vitepress_path

    ctx.actions.write(output, json.encode(path_map))

    return [DefaultInfo(files = depset([output]))]

_path_map = rule(
    implementation = _path_map_impl,
    attrs = {
        "content": attr.label_list(
            providers = [VitePressContentInfo],
            doc = "vitepress_filegroup targets to generate path map for.",
        ),
    },
)

def _rewrite_impl(ctx):
    """Run the link rewriter against assembled content."""
    output_dir = ctx.actions.declare_directory(ctx.attr.name)

    content_dir = ctx.files.assembled[0]  # The assembled directory
    path_map_file = ctx.files.path_map[0]

    ctx.actions.run(
        executable = ctx.executable.rewriter,
        arguments = [
            "--content-dir",
            content_dir.path,
            "--path-map",
            path_map_file.path,
            "--output-dir",
            output_dir.path,
        ],
        inputs = [content_dir, path_map_file],
        outputs = [output_dir],
        mnemonic = "VitePressRewrite",
        progress_message = "Rewriting links in VitePress content",
    )

    return [DefaultInfo(files = depset([output_dir]))]

_rewrite = rule(
    implementation = _rewrite_impl,
    attrs = {
        "assembled": attr.label(
            doc = "The assembled content directory.",
            mandatory = True,
        ),
        "path_map": attr.label(
            doc = "The path map JSON file.",
            mandatory = True,
            allow_single_file = [".json"],
        ),
        "rewriter": attr.label(
            doc = "The link rewriter binary.",
            default = "//bazel/vitepress/rewriter:rewrite",
            executable = True,
            cfg = "exec",
        ),
    },
)

def vitepress_site(
        name,
        content,
        wrangler_project,
        vitepress_config = ".vitepress/config.js",
        extra_srcs = [],
        extra_deps = [],
        visibility = None):
    """High-level macro for building and deploying a VitePress documentation site.

    Creates a pipeline: assemble → path_map → rewrite → vite_build → wrangler_pages.

    Args:
        name: Base name for generated targets.
        content: List of vitepress_filegroup targets to include.
        wrangler_project: Cloudflare Pages project name.
        vitepress_config: Path to VitePress config file.
        extra_srcs: Additional source files for the VitePress build.
        extra_deps: Additional npm dependencies.
        visibility: Target visibility.
    """

    # Step 1: Assemble content from all sources
    _assemble(
        name = name + "_assemble",
        content = content,
    )

    # Step 2: Generate path map
    _path_map(
        name = name + "_path_map",
        content = content,
    )

    # Step 3: Rewrite links
    _rewrite(
        name = name + "_rewrite",
        assembled = ":" + name + "_assemble",
        path_map = ":" + name + "_path_map",
    )

    # Step 4: Build with VitePress
    # The rewritten content directory is passed as a Bazel dep
    vite_build(
        name = "build",
        srcs = [
            "package.json",
            ":" + name + "_rewrite",
        ] + extra_srcs,
        tool = ":vitepress",
        config = vitepress_config,
        build_args = ["build", "--outDir", "dist"],
        deps = [
            "vitepress",
            "vue",
        ] + extra_deps,
        visibility = ["//visibility:public"],
    )

    # Step 5: Cloudflare Pages deployment
    wrangler_pages(
        name = name,
        dist = ":build_dist",
        project_name = wrangler_project,
        visibility = visibility or ["//projects/websites:__pkg__"],
        wrangler = ":wrangler",
    )
