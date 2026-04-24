#!/bin/bash
# PreToolUse hook: warn when writing a Helm Deployment template where
# spec.selector.matchLabels uses a shared selectorLabels include helper
# without app.kubernetes.io/component.
#
# In a chart with multiple Deployments, pods share generic name+instance
# selector labels. Without a component label, Services route traffic to
# pods from ALL Deployments instead of the intended one. See PR #2181.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr)
# Exit 2: block (not used — this is advisory only)

set -euo pipefail

INPUT=$(cat)

# Only trigger on Helm chart deployment template files
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Match deployment templates in chart/ or deploy/ template directories
BASENAME=$(basename "$FILE_PATH")
DIRPATH=$(dirname "$FILE_PATH")
if [[ "$DIRPATH" != *chart/templates* ]] && [[ "$DIRPATH" != *deploy/templates* ]]; then
	exit 0
fi
if [[ "$BASENAME" != *deployment* ]] && [[ "$BASENAME" != *Deployment* ]]; then
	exit 0
fi

# Get the content being written (Write tool) or the replacement string (Edit tool)
NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty')
if [[ -z "$NEW_CONTENT" ]]; then
	exit 0
fi

# Skip if no matchLabels present
if ! echo "$NEW_CONTENT" | grep -q 'matchLabels:'; then
	exit 0
fi
# Skip if no selectorLabels include present
if ! echo "$NEW_CONTENT" | grep -qE 'include\s+"[^"]*[Ss]electorLabels'; then
	exit 0
fi

# Use awk to detect matchLabels block with selectorLabels include but without component label.
# Sliding-window: after seeing matchLabels: then include "*.selectorLabels", check the next line.
HAS_ISSUE=$(echo "$NEW_CONTENT" | awk '
  prev_selector {
    if ($0 !~ /app\.kubernetes\.io\/component:/) { print "yes"; exit }
    prev_selector = 0
  }
  /matchLabels:/ { expect_include = 1; next }
  expect_include && /include[[:space:]]+"[^"]*[Ss]electorLabels/ {
    prev_selector = 1
    expect_include = 0
    next
  }
  { expect_include = 0 }
')

if [[ "$HAS_ISSUE" == "yes" ]]; then
	cat >&2 <<-EOF
		WARNING: Deployment selector uses selectorLabels include without app.kubernetes.io/component.

		In a chart with multiple Deployments, all pods share the same name+instance
		selector labels. Services will route traffic to pods from ALL Deployments
		instead of the intended one (PR #2181).

		Add app.kubernetes.io/component: <component> to both:
		  - spec.selector.matchLabels
		  - spec.template.metadata.labels

		Example:
		  matchLabels:
		    {{- include "mychart.selectorLabels" . | nindent 6 }}
		    app.kubernetes.io/component: api

		If this chart has only one Deployment, proceed. Otherwise add the component label.
	EOF
fi

exit 0
