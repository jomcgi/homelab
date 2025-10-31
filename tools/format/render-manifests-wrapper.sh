#!/usr/bin/env bash
# Wrapper script to build all Helm manifests with Bazel caching
set -euo pipefail

echo "🔨 Rendering all Helm manifests (with caching)..."
bazel build //tools/argocd-parallel:render_all_parallel

echo "✅ All manifests rendered!"
