#!/usr/bin/env bash
set -euo pipefail

# Discovery script: lists all available Bazel targets organized by category.

cat <<'HELP'
HOMELAB BAZEL TARGETS
=====================

FORMATTING & BUILDS:
  format                                          Format code + render all manifests
  bazel build //...                               Build all targets
  bazel test //...                                Run all tests

CLUSTER INSPECTION (read-only):
  bazel run //bazel/tools/cluster:pods             List pods in key namespaces
  bazel run //bazel/tools/cluster:events           Recent cluster events
  bazel run //bazel/tools/cluster:status           Cluster health summary
  bazel run //bazel/tools/cluster:argocd           ArgoCD sync status

MANIFEST RENDERING:
  bazel run //projects/<project>/<svc>/deploy:render_manifests   Render Helm manifests for a service

CONTAINER IMAGES:
  bazel run //charts/<svc>/image:push             Push specific container image

TOOLS:
  bazel run //bazel/tools:help                     Show this help message
  bazel run //bazel/tools:workspace_status         Show workspace status

QUERYING:
  bazel query //bazel/tools/cluster/...                 List all cluster targets
  bazel query //projects/<project>/<svc>/deploy:*  List all targets for a service
  bazel query //charts/<svc>/...                  List all targets for a chart
HELP
