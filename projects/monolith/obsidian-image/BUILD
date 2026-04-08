# gazelle:ignore

load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

# Export entrypoint.sh so it can be referenced by Helm chart tests that verify
# the /tmp/ready sentinel path is consistent with the readiness probe in deployment.yaml.
exports_files(["entrypoint.sh"])

# Package obsidian-headless CLI with all transitive JavaScript dependencies.
# pnpm hoist=false means transitive deps (bindings, file-uri-to-path) are not
# siblings of obsidian-headless — they must be listed explicitly.
# Native addon (better-sqlite3 .node binary) is handled via multiarch_tars.
genrule(
    name = "obsidian_headless_tar",
    srcs = [
        "//:node_modules/obsidian-headless",
        "//:node_modules/bindings",
        "//:node_modules/file-uri-to-path",
    ],
    outs = ["obsidian_headless.tar"],
    cmd = """
        set -e
        WORK=$$(mktemp -d)
        DEST="$$WORK/usr/local/lib"
        mkdir -p "$$DEST"
        # Copy obsidian-headless and its direct deps (commander, better-sqlite3)
        SRC_DIR=$$(echo '$(locations //:node_modules/obsidian-headless)' | tr ' ' '\\n' | grep 'obsidian-headless$$' | head -1)
        MODULES_DIR=$$(dirname "$$SRC_DIR")
        cp -rL "$$MODULES_DIR" "$$DEST/node_modules"
        # Copy transitive deps of better-sqlite3 not present as siblings
        BINDINGS_DIR=$$(echo '$(locations //:node_modules/bindings)' | tr ' ' '\\n' | grep '/bindings$$' | head -1)
        cp -rL "$$BINDINGS_DIR" "$$DEST/node_modules/bindings"
        FUTP_DIR=$$(echo '$(locations //:node_modules/file-uri-to-path)' | tr ' ' '\\n' | grep '/file-uri-to-path$$' | head -1)
        cp -rL "$$FUTP_DIR" "$$DEST/node_modules/file-uri-to-path"
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
#   tars: obsidian-headless CLI + JS deps, entrypoint script
#   multiarch_tars: better-sqlite3 native addon (per-arch prebuilt from GitHub releases)
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@obsidian_image_lock//:contents",
    multiarch_tars = [
        "@better_sqlite3//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/projects/monolith/obsidian-image",
    tars = [
        ":obsidian_headless_tar",
        ":entrypoint_tar",
    ],
)
