load("@npm//:defs.bzl", "npm_link_all_packages")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

npm_link_all_packages(name = "node_modules")

pkg_tar(
    name = "src_tar",
    srcs = glob(["src/**/*.ts"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app/src",
    strip_prefix = "src",
)

pkg_tar(
    name = "config_tar",
    srcs = [
        "package.json",
        "tsconfig.json",
    ],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "app",
)

genrule(
    name = "node_modules_tar",
    srcs = [
        ":node_modules/@chat-adapter/discord",
        ":node_modules/chat",
        ":node_modules/nats",
        ":node_modules/tsx",
    ],
    outs = ["node_modules_tar.tar"],
    cmd = """
        set -euo pipefail
        mkdir -p tmp/app/node_modules/.bin

        # Find all package.json files in the deps and copy each package
        find -L $(SRCS) -name package.json -type f 2>/dev/null | while IFS= read -r pkg; do
            PKG_DIR="$$(dirname "$$pkg")"
            PACKAGE_NAME=$$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "$$pkg" | head -1 | cut -d'"' -f4 || true)

            if [ -z "$$PACKAGE_NAME" ]; then
                continue
            fi

            # Determine target directory
            if echo "$$PACKAGE_NAME" | grep -q '^@'; then
                SCOPE=$$(echo "$$PACKAGE_NAME" | cut -d'/' -f1)
                PKG_NAME=$$(echo "$$PACKAGE_NAME" | cut -d'/' -f2)
                TARGET_DIR="tmp/app/node_modules/$$SCOPE/$$PKG_NAME"
            else
                TARGET_DIR="tmp/app/node_modules/$$PACKAGE_NAME"
            fi

            # Skip if already copied
            if [ -d "$$TARGET_DIR" ]; then
                continue
            fi

            mkdir -p "$$(dirname "$$TARGET_DIR")"
            cp -rL "$$PKG_DIR" "$$TARGET_DIR" 2>/dev/null || true
        done

        tar -C tmp -czf $@ .
    """,
)

apko_image(
    name = "image",
    config = "//projects/agent_platform/chat_bot/image:apko.yaml",
    contents = "@chat_bot_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/projects/agent-platform/chat-bot",
    tars = [
        ":src_tar",
        ":config_tar",
        ":node_modules_tar",
    ],
)
