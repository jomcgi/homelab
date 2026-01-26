#!/usr/bin/env bash
# Only update Python requirements if they're out of sync with pyproject.toml
set -euo pipefail

# Quick check: are requirements in sync?
if bazel test //requirements:runtime_test 2>/dev/null; then
	echo "✓ Python requirements in sync"
	exit 0
fi

echo "Python requirements out of sync, regenerating..."
bazel run //requirements:runtime
bazel run //requirements:requirements.all

# Stage the updated lock files
git add requirements/*.txt 2>/dev/null || true
echo "✓ Python requirements updated and staged"
