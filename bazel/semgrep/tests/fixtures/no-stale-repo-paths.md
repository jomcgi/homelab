# Test fixtures for the no-stale-repo-paths semgrep rule.
#
# Annotations:
#   # ruleid: no-stale-repo-paths  — the next non-annotation line MUST be flagged
#   # ok: no-stale-repo-paths      — the next non-annotation line MUST NOT be flagged

## Positive examples (should be flagged)

The following reference an old overlays/prod/ path:

# ruleid: no-stale-repo-paths
overlays/prod/values.yaml

Old Bazel target for a service binary:

# ruleid: no-stale-repo-paths
//services/myapp:image

Old Bazel target for a Helm chart:

# ruleid: no-stale-repo-paths
//charts/mychart:chart

## Negative examples (should not be flagged)

Current GitOps deploy path:

# ok: no-stale-repo-paths
projects/myservice/deploy/values.yaml

Current Helm chart path:

# ok: no-stale-repo-paths
projects/myservice/chart/Chart.yaml

Current Bazel target under projects/:

# ok: no-stale-repo-paths
//projects/myservice/image:push

A word that merely contains the substring "services" but is not a Bazel target:

# ok: no-stale-repo-paths
This document describes the services architecture.
