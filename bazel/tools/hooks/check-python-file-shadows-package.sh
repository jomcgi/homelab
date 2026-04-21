#!/bin/bash
# PreToolUse hook: warns when creating or editing a Python file whose name
# (stem, without .py) matches a pip dependency from pyproject.toml.
#
# This catches the shadowing bug from PR #2114 where app/mcp.py shadowed
# the `mcp` pip package, causing unexpected import resolution at runtime.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only — never blocks)
# Exit 2: not used

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# No file path — nothing to check
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Only check .py files
if [[ "$FILE_PATH" != *.py ]]; then
	exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Skip __init__.py
if [[ "$BASENAME" == "__init__.py" ]]; then
	exit 0
fi

# Skip test directories and test files
if [[ "$FILE_PATH" == */test/* ]] || [[ "$FILE_PATH" == */tests/* ]] || [[ "$BASENAME" == *_test.py ]]; then
	exit 0
fi

# Extract stem (filename without .py extension)
STEM="${BASENAME%.py}"

# Locate pyproject.toml — allow override via env var for testing
if [[ -n "${PYPROJECT_TOML_PATH:-}" ]]; then
	PYPROJECT="$PYPROJECT_TOML_PATH"
else
	# Walk up from the file's directory to find an existing dir for git
	FILE_DIR=$(dirname "$FILE_PATH")
	while [[ ! -d "$FILE_DIR" ]] && [[ "$FILE_DIR" != "/" ]]; do
		FILE_DIR=$(dirname "$FILE_DIR")
	done
	REPO_ROOT=$(git -C "$FILE_DIR" rev-parse --show-toplevel 2>/dev/null) || REPO_ROOT="$PWD"
	PYPROJECT="$REPO_ROOT/pyproject.toml"
fi

if [[ ! -f "$PYPROJECT" ]]; then
	exit 0
fi

# Parse [project.dependencies] from pyproject.toml with an inline Python script.
# Normalize hyphens → underscores for comparison (PEP 503 canonical form).
MATCHED=$(python3 - "$STEM" "$PYPROJECT" <<'PYTHON'
import sys
import re

stem = sys.argv[1].lower().replace("-", "_")
pyproject_path = sys.argv[2]

in_deps = False
with open(pyproject_path) as f:
    for line in f:
        stripped = line.strip()

        # Detect start of another TOML section — exit dep block
        if stripped.startswith("[") and not stripped.startswith("#"):
            in_deps = False

        # Detect start of dependencies array (handles "dependencies = [" or
        # "dependencies=[")
        if re.match(r'^dependencies\s*=\s*\[', stripped):
            in_deps = True
            continue

        if in_deps:
            if stripped.startswith("]"):
                break

            # Extract package name: first identifier before any specifier/extra
            m = re.match(r'"([A-Za-z0-9][A-Za-z0-9._-]*)', stripped)
            if not m:
                continue

            name = m.group(1)
            name_norm = name.lower().replace("-", "_")
            if name_norm == stem:
                print(name)
                break
PYTHON
) || true

if [[ -n "$MATCHED" ]]; then
	cat >&2 <<-EOF
		WARNING: '$BASENAME' shadows pip package '$MATCHED'.

		File: $FILE_PATH

		Python resolves imports by searching sys.path in order. A local file
		named after an installed package will be imported instead of the package
		(PR #2114: app/mcp.py shadowed the mcp package, breaking MCP transport).

		Consider renaming '$BASENAME' to avoid this conflict.
	EOF
fi

exit 0
