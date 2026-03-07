"""npm_package_tar - Download an npm package and create an OCI tar layer.

Downloads a package tarball from the npm registry, extracts it, and creates
a tar suitable for inclusion in an apko_image as a layer. The package is
installed at /usr/local/lib/node_modules/<scope>/<name>/ with a symlink
in /usr/local/bin/.
"""

def _npm_package_tar_impl(repository_ctx):
    """Download npm package and create an installable tar."""

    # Download the npm tarball
    repository_ctx.download(
        url = repository_ctx.attr.url,
        output = "package.tgz",
        sha256 = repository_ctx.attr.sha256,
    )

    package_name = repository_ctx.attr.package_name
    bin_name = repository_ctx.attr.bin_name
    bin_entry = repository_ctx.attr.bin_entry
    install_dir = "usr/local/lib/node_modules/" + package_name

    # Extract, repackage, and create symlink in a single script
    repository_ctx.file("BUILD.bazel", """
genrule(
    name = "tar",
    srcs = ["package.tgz"],
    outs = ["package.tar"],
    cmd = \"\"\"
        set -e
        WORK=$$(mktemp -d)
        mkdir -p "$$WORK/{install_dir}"
        tar -xzf $< -C "$$WORK/{install_dir}" --strip-components=1
        chmod 755 "$$WORK/{install_dir}/{bin_entry}"
        mkdir -p "$$WORK/usr/local/bin"
        ln -s "../lib/node_modules/{package_name}/{bin_entry}" "$$WORK/usr/local/bin/{bin_name}"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    \"\"\",
    visibility = ["//visibility:public"],
)
""".format(
        install_dir = install_dir,
        bin_entry = bin_entry,
        bin_name = bin_name,
        package_name = package_name,
    ))

npm_package_tar = repository_rule(
    implementation = _npm_package_tar_impl,
    attrs = {
        "url": attr.string(
            mandatory = True,
            doc = "URL of the npm package tarball (.tgz)",
        ),
        "sha256": attr.string(
            mandatory = True,
            doc = "SHA256 checksum of the tarball",
        ),
        "package_name": attr.string(
            mandatory = True,
            doc = "Full package name including scope (e.g., '@anthropic-ai/claude-code')",
        ),
        "bin_name": attr.string(
            mandatory = True,
            doc = "Name of the binary symlink to create in /usr/local/bin",
        ),
        "bin_entry": attr.string(
            mandatory = True,
            doc = "Entrypoint file relative to the package root (e.g., 'cli.js')",
        ),
    },
    doc = """Download an npm package and create an OCI image tar layer.

Creates a tar with the package at /usr/local/lib/node_modules/<package_name>/
and a symlink at /usr/local/bin/<bin_name>.

Example:
    npm_package_tar(
        name = "claude_code",
        url = "https://registry.npmjs.org/@anthropic-ai/claude-code/-/claude-code-2.1.71.tgz",
        sha256 = "...",
        package_name = "@anthropic-ai/claude-code",
        bin_name = "claude",
        bin_entry = "cli.js",
    )

Then in BUILD files:
    apko_image(
        name = "my_image",
        tars = ["@claude_code//:tar"],
    )
""",
)
