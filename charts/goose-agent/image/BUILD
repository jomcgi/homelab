load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Goose config into the image at ~/.config/goose/config.yaml
pkg_tar(
    name = "config_tar",
    srcs = ["config.yaml"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/.config/goose",
)

# Package Claude Code CLI from the pnpm lockfile-managed npm package.
# Places the package at /usr/local/lib/node_modules/@anthropic-ai/claude-code/
# with a symlink at /usr/local/bin/claude for PATH discovery.
genrule(
    name = "claude_code_tar",
    srcs = ["//:node_modules/@anthropic-ai/claude-code"],
    outs = ["claude_code.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/@anthropic-ai/claude-code"
        mkdir -p "$$DEST"
        # Find the source directory (follow symlinks with -L)
        SRC_DIR=$$(echo '$(locations //:node_modules/@anthropic-ai/claude-code)' | tr ' ' '\\n' | grep 'claude-code$$' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/cli.js"
        mkdir -p "$$WORK/usr/local/bin"
        ln -s "../lib/node_modules/@anthropic-ai/claude-code/cli.js" "$$WORK/usr/local/bin/claude"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Build the goose-agent image:
#   apko base: bash, git, gh, go, node, pnpm (from Wolfi)
#   multiarch tars: goose binary, bb (BuildBuddy CLI)
#   regular tars: Goose config, Claude Code CLI (npm package)
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@goose_agent_lock//:contents",
    multiarch_tars = [
        "@goose//:tar",
        "@bb//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/goose-agent",
    tars = [
        ":config_tar",
        ":claude_code_tar",
    ],
)
