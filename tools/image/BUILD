load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

# Symlinks from /tools/bin/ to actual binary locations.
# bootstrap.sh extracts /tools/bin/* from the image into .tools/bin/
pkg_tar(
    name = "tools_bin_symlinks",
    symlinks = {
        # Formatters (Wolfi packages install to /usr/bin/)
        "/tools/bin/ruff": "/usr/bin/ruff",
        "/tools/bin/shfmt": "/usr/bin/shfmt",
        "/tools/bin/gofumpt": "/usr/bin/gofumpt",
        # Developer tools
        "/tools/bin/go": "/usr/bin/go",
        "/tools/bin/node": "/usr/bin/node",
        "/tools/bin/pnpm": "/usr/bin/pnpm",
        "/tools/bin/python": "/usr/bin/python3",
        "/tools/bin/git": "/usr/bin/git",
        "/tools/bin/gh": "/usr/bin/gh",
    },
)

# Package prettier from the pnpm lockfile-managed npm package.
# Places the package at /usr/local/lib/node_modules/prettier/
# with a symlink at /tools/bin/prettier for PATH discovery.
genrule(
    name = "prettier_tar",
    srcs = ["//:node_modules/prettier"],
    outs = ["prettier.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/prettier"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(locations //:node_modules/prettier)' | tr ' ' '\\n' | grep 'prettier$$' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/bin/prettier.cjs"
        mkdir -p "$$WORK/tools/bin"
        ln -s "../../usr/local/lib/node_modules/prettier/bin/prettier.cjs" "$$WORK/tools/bin/prettier"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@homelab_tools_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab-tools",
    tars = [
        ":tools_bin_symlinks",
        ":prettier_tar",
    ],
)
