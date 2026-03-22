# gazelle:semgrep disabled
# gazelle:ignore

load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_go//go:def.bzl", "go_test")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//bazel/semgrep/defs:defs.bzl", "semgrep_test")
load("//bazel/tools/oci:apko_image.bzl", "apko_image")

filegroup(
    name = "recipe_files",
    srcs = glob(["recipes/*.yaml"]),
    visibility = ["//projects/agent_platform/orchestrator:__pkg__"],
)

# Validate that Goose recipe YAML files are well-formed and use safe template patterns.
# Run locally: bazel test //projects/agent_platform/goose_agent/image:recipe_validate_test
go_test(
    name = "recipe_validate_test",
    srcs = ["recipe_validate_test.go"],
    embedsrcs = glob(["recipes/*.yaml"]),
    importpath = "github.com/jomcgi/homelab/projects/agent_platform/goose_agent/image",
    deps = ["@in_gopkg_yaml_v3//:yaml_v3"],
)

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

# Cross-compile runner binary for amd64
platform_transition_filegroup(
    name = "runner_amd64_bin",
    srcs = ["//projects/agent_platform/orchestrator/cmd/runner"],
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
    srcs = ["//projects/agent_platform/orchestrator/cmd/runner"],
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
    repository = "ghcr.io/jomcgi/homelab/projects/agent_platform/goose_agent/image",
    tars = [
        ":config_tar",
        ":claude_code_tar",
    ],
)

go_test(
    name = "image_test",
    srcs = ["recipe_validate_test.go"],
    embedsrcs = glob(["recipes/*.yaml"]),
    deps = ["@in_gopkg_yaml_v3//:yaml_v3"],
)

# Enforce Goose recipe schema rules on all recipe YAML files and the base config.
# Catches unsupported extension fields (e.g. headers: in streamable_http) that
# Goose's serde_yaml rejects at runtime with "Invalid recipe: did not find expected key".
semgrep_test(
    name = "recipes_semgrep_test",
    srcs = glob(["recipes/*.yaml"]) + ["config.yaml"],
    rules = ["//bazel/semgrep/rules:yaml_rules"],
    tags = ["semgrep"],
)
