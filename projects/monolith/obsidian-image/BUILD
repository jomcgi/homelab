# gazelle:ignore

load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Package the obsidian-headless npm CLI and all transitive dependencies.
# In pnpm/rules_js, deps are siblings under the same node_modules/ directory.
# We copy the entire parent node_modules tree to get obsidian-headless + all deps,
# then create a /usr/local/bin/ob symlink for PATH discovery.
genrule(
    name = "obsidian_headless_tar",
    srcs = ["//:node_modules/obsidian-headless"],
    outs = ["obsidian_headless.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib"
        mkdir -p "$$DEST"
        # Find the obsidian-headless package, then go up to its parent node_modules/
        # to capture all transitive dependencies as siblings
        SRC_DIR=$$(echo '$(locations //:node_modules/obsidian-headless)' | tr ' ' '\\n' | grep 'obsidian-headless$$' | head -1)
        MODULES_DIR=$$(dirname "$$SRC_DIR")
        cp -rL "$$MODULES_DIR" "$$DEST/node_modules"
        chmod 755 "$$DEST/node_modules/obsidian-headless/cli.js"
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

# Build the obsidian sidecar image:
#   apko base: bash, nodejs (from Wolfi)
#   tars: obsidian-headless CLI + deps, entrypoint script
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@obsidian_image_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/obsidian-image",
    tars = [
        ":obsidian_headless_tar",
        ":entrypoint_tar",
    ],
)
