#!/bin/bash
# PreToolUse hook: warns when writing a SQL migration file whose timestamp prefix
# (first 14 chars of filename) collides with an existing file in the same
# migrations/ directory.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning)
# Exit 2: block the operation

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check .sql files under a migrations/ directory
if [[ -z "$FILE_PATH" ]] || [[ "$FILE_PATH" != */migrations/*.sql ]]; then
	exit 0
fi

FILENAME=$(basename "$FILE_PATH")

# Version prefix = first 14 characters (e.g. 20240301120000 from 20240301120000_create_users.sql)
if [[ ${#FILENAME} -lt 14 ]]; then
	exit 0
fi

VERSION_PREFIX="${FILENAME:0:14}"

# Must be numeric
if ! [[ "$VERSION_PREFIX" =~ ^[0-9]{14}$ ]]; then
	exit 0
fi

MIGRATIONS_DIR=$(dirname "$FILE_PATH")

# Look for any OTHER .sql file in the same directory with the same prefix
DUPLICATES=$(find "$MIGRATIONS_DIR" -maxdepth 1 -name "${VERSION_PREFIX}*.sql" ! -name "$FILENAME" 2>/dev/null || true)

if [[ -n "$DUPLICATES" ]]; then
	cat >&2 <<-EOF
		WARNING: Duplicate migration version prefix detected.

		The file you are writing:
		  $FILE_PATH

		shares the version prefix "$VERSION_PREFIX" with:
		$(echo "$DUPLICATES" | sed 's/^/  /')

		Each migration file must have a unique 14-digit timestamp prefix.
		Please pick a different version number before writing this file.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
