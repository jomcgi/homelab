load("//tools/oci:apko_image.bzl", "apko_image")
load(":multitool_tar.bzl", "multitool_tar")

multitool_tar(
    name = "tools_tar",
    tools = [
        "argocd",
        "buildozer",
        "crane",
        "gazelle",
        "gh",
        "gofumpt",
        "helm",
        "kind",
        "op",
        "ruff",
        "shfmt",
    ],
)

# Package prettier from the pnpm lockfile-managed npm package.
# Places the package at /usr/local/lib/node_modules/prettier/
# with a symlink at /usr/bin/prettier for PATH discovery.
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
        mkdir -p "$$WORK/usr/bin"
        ln -s "../local/lib/node_modules/prettier/bin/prettier.cjs" "$$WORK/usr/bin/prettier"
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
        ":prettier_tar",
    ],
)
