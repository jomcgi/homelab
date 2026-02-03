"""esbuild build macro for TypeScript bundling.

This macro provides a unified interface for TypeScript compilation and bundling
using ts_project and esbuild. It creates two targets:
  - {name}: The bundled JavaScript output
  - {name}_dist: A directory containing all distributable files (JS, CSS, assets)
"""

load("@aspect_rules_esbuild//esbuild:defs.bzl", "esbuild")
load("@aspect_rules_js//js:defs.bzl", "js_library")
load("@aspect_rules_ts//ts:defs.bzl", "ts_project")

def esbuild_build(
        name,
        srcs,
        entry_point,
        tsconfig = None,
        deps = [],
        data = [],
        css_srcs = [],
        define = {},
        external = [],
        platform = "browser",
        target = "es2020",
        minify = True,
        sourcemap = True,
        splitting = False,
        format = "esm",
        visibility = None):
    """Build a TypeScript project with esbuild bundling.

    Args:
        name: Base name for the generated targets.
        srcs: TypeScript source files.
        entry_point: Main entry point for bundling.
        tsconfig: Path to tsconfig.json (optional, uses default if not specified).
        deps: Dependencies for TypeScript compilation.
        data: Runtime data files (assets, etc.).
        css_srcs: CSS files to bundle alongside the JavaScript.
        define: esbuild define replacements (e.g., {"process.env.NODE_ENV": '"production"'}).
        external: Packages to exclude from the bundle.
        platform: Target platform ("browser", "node", or "neutral").
        target: ECMAScript target version.
        minify: Whether to minify the output.
        sourcemap: Whether to generate source maps.
        splitting: Enable code splitting (only works with format="esm").
        format: Output format ("esm", "cjs", or "iife").
        visibility: Visibility of the generated targets.
    """
    ts_name = name + "_ts"
    bundle_name = name + "_bundle"

    # TypeScript compilation
    ts_project(
        name = ts_name,
        srcs = srcs,
        tsconfig = tsconfig,
        deps = deps,
        declaration = True,
        source_map = sourcemap,
        visibility = ["//visibility:private"],
    )

    # esbuild bundling
    esbuild(
        name = bundle_name,
        srcs = [":" + ts_name],
        entry_point = entry_point,
        define = define,
        external = external,
        platform = platform,
        target = target,
        minify = minify,
        sourcemap = "external" if sourcemap else False,
        splitting = splitting,
        format = format,
        visibility = ["//visibility:private"],
    )

    # Collect CSS files if provided
    css_deps = []
    if css_srcs:
        css_lib_name = name + "_css"
        js_library(
            name = css_lib_name,
            srcs = css_srcs,
            visibility = ["//visibility:private"],
        )
        css_deps = [":" + css_lib_name]

    # Main target - expose the bundle
    js_library(
        name = name,
        srcs = [":" + bundle_name],
        data = data + css_deps,
        visibility = visibility,
    )

    # Dist target - all distributable files
    native.filegroup(
        name = name + "_dist",
        srcs = [":" + bundle_name] + css_srcs + data,
        visibility = visibility,
    )
