#!/usr/bin/env bash
# Validate that atlas.sum is up-to-date with the migration SQL files.
# Used as a Bazel sh_test to catch stale checksums in CI.
set -euo pipefail

ATLAS="${ATLAS_BIN:?ATLAS_BIN must be set}"
DIR="${MIGRATIONS_DIR:?MIGRATIONS_DIR must be set}"

# atlas migrate validate checks that atlas.sum matches the migration files
"$ATLAS" migrate validate --dir "file://$DIR" 2>&1
echo "PASS: atlas.sum is up-to-date for $DIR"
