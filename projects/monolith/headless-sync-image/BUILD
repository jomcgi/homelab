# gazelle:ignore

load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Package the obsidian-headless npm CLI from the pnpm lockfile.
# Places the package at /usr/local/lib/node_modules/obsidian-headless/
# with a symlink at /usr/local/bin/ob for PATH discovery.
genrule(
    name = "obsidian_headless_tar",
    srcs = ["//:node_modules/obsidian-headless"],
    outs = ["obsidian_headless.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib/node_modules/obsidian-headless"
        mkdir -p "$$DEST"
        SRC_DIR=$$(echo '$(locations //:node_modules/obsidian-headless)' | tr ' ' '\\n' | grep 'obsidian-headless$$' | head -1)
        cp -rL "$$SRC_DIR/." "$$DEST/"
        chmod 755 "$$DEST/cli.js"
        mkdir -p "$$WORK/usr/local/bin"
        ln -s "../lib/node_modules/obsidian-headless/cli.js" "$$WORK/usr/local/bin/ob"
        tar -cf $@ -C "$$WORK" .
        rm -rf "$$WORK"
    """,
)

# Package the entrypoint script.
tar(
    name = "entrypoint_tar",
    srcs = ["entrypoint.sh"],
    mtree = [
        "./usr/local/bin/entrypoint.sh type=file content=$(execpath entrypoint.sh) mode=0755 uid=0 gid=0",
    ],
)

# Build the headless-sync image:
#   apko base: bash, nodejs (from Wolfi)
#   tars: obsidian-headless CLI, entrypoint script
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@headless_sync_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/headless-sync-image",
    tars = [
        ":obsidian_headless_tar",
        ":entrypoint_tar",
    ],
)
