#!/bin/bash
# PreToolUse hook: warns when writing/editing BUILD or BUILD.bazel files that package
# npm modules into apko container images via a genrule. Under pnpm's strict no-hoist
# layout, each package lives in its own isolated node_modules/ subtree — listing a
# single node_modules/<pkg> in genrule srcs will omit all transitive dependencies,
# causing runtime "Cannot find module" errors inside the container.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only, not a blocker)

set -euo pipefail

INPUT=$(cat)

# Extract file path and content from Write (content) or Edit (new_string) tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Only check BUILD and BUILD.bazel files
if ! echo "$FILE_PATH" | grep -qE '.*/BUILD(\.bazel)?$'; then
	exit 0
fi

# Must reference apko_image (otherwise not an apko image build)
if ! echo "$CONTENT" | grep -qF 'apko_image'; then
	exit 0
fi

# Must have a genrule that references node_modules/ in srcs
if ! echo "$CONTENT" | grep -qF 'node_modules/'; then
	exit 0
fi

# Must have a genrule that produces a .tar output (apko layer tarball)
if ! echo "$CONTENT" | grep -qE '\.tar["\)]'; then
	exit 0
fi

cat >&2 <<-'EOF'
	WARNING: This BUILD file packages npm modules into an apko image via a genrule.
	Under pnpm's strict no-hoist layout, each package is isolated in its own
	node_modules/ subtree. Listing a single node_modules/<pkg> path in genrule srcs
	will omit all transitive dependencies, causing runtime "Cannot find module" errors
	inside the container.

	Ensure ALL transitive dependencies are listed explicitly in the genrule srcs, or
	use a glob pattern that captures the full dependency subtree.

	See also: bazel/semgrep/rules/bazel/single-npm-package-in-apko-genrule.yaml
EOF

exit 0
