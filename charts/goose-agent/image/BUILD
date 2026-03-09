load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//tools/oci:apko_image.bzl", "apko_image")

# Package the Goose config into the image at ~/.config/goose/config.yaml
pkg_tar(
    name = "config_tar",
    srcs = ["config.yaml"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/.config/goose",
)

# Package Goose recipes into the image at ~/recipes/
pkg_tar(
    name = "recipes_tar",
    srcs = glob(["recipes/*.yaml"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/recipes",
)

# Validate recipe YAML files on every PR.
# Checks required fields and guards against the double-quoted template-variable
# anti-pattern that produces invalid YAML after MiniJinja rendering.
sh_test(
    name = "recipe_yaml_test",
    srcs = ["validate-recipes.sh"],
    args = [
        "$(rootpath recipes/ci-debug.yaml)",
        "$(rootpath recipes/code-fix.yaml)",
    ],
    data = glob(["recipes/*.yaml"]),
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

# Cross-compile runner binary for amd64
platform_transition_filegroup(
    name = "runner_amd64_bin",
    srcs = ["//services/agent-orchestrator/cmd/runner"],
    target_platform = "@rules_go//go/toolchain:linux_amd64",
)

# Package runner binary for amd64
tar(
    name = "runner_tar_amd64",
    srcs = [":runner_amd64_bin"],
    mtree = [
        "./usr/local/bin/agent-runner type=file content=$(execpath :runner_amd64_bin) mode=0755 uid=0 gid=0",
    ],
)

# Cross-compile runner binary for arm64
platform_transition_filegroup(
    name = "runner_arm64_bin",
    srcs = ["//services/agent-orchestrator/cmd/runner"],
    target_platform = "@rules_go//go/toolchain:linux_arm64",
)

# Package runner binary for arm64
tar(
    name = "runner_tar_arm64",
    srcs = [":runner_arm64_bin"],
    mtree = [
        "./usr/local/bin/agent-runner type=file content=$(execpath :runner_arm64_bin) mode=0755 uid=0 gid=0",
    ],
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
        ":runner_tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/goose-agent",
    tars = [
        ":config_tar",
        ":claude_code_tar",
        ":recipes_tar",
    ],
)
