#!/usr/bin/env bash
# Update Python requirements lock files from pyproject.toml
set -euo pipefail

echo "Updating Python requirements..."

# Regenerate runtime.txt from pyproject.toml
bazel run //requirements:runtime

# Regenerate all.txt (includes test/tools dependencies)
bazel run //requirements:requirements.all

echo "✅ Python requirements updated"
