#!/usr/bin/env bash
# Push script for Cloudflare Pages deployment
# Uses wrangler CLI to deploy built assets

set -o errexit -o nounset -o pipefail

# Bazel runfiles setup - adapted from rules_oci for bazel run compatibility
RUNFILES_DIR="${RUNFILES_DIR:-}"
if [[ -z "$RUNFILES_DIR" ]]; then
  # When run via bazel run, set RUNFILES_DIR to script location + .runfiles
  RUNFILES_DIR="$0.runfiles"
fi

if [[ -f "${RUNFILES_DIR}/bazel_tools/tools/bash/runfiles/runfiles.bash" ]]; then
  source "${RUNFILES_DIR}/bazel_tools/tools/bash/runfiles/runfiles.bash"
elif [[ -f "${RUNFILES_MANIFEST_FILE:-/dev/null}" ]]; then
  source "$(grep -m1 "^bazel_tools/tools/bash/runfiles/runfiles.bash " \
    "$RUNFILES_MANIFEST_FILE" | cut -d ' ' -f 2-)"
else
  echo >&2 "ERROR: cannot find @bazel_tools//tools/bash/runfiles:runfiles.bash"
  exit 1
fi

readonly WRANGLER="$(rlocation "{{WRANGLER}}")"
readonly DIST_DIR="$(rlocation "{{DIST_DIR}}")"
readonly PROJECT_NAME="{{PROJECT_NAME}}"
readonly BRANCH="{{BRANCH}}"

# Verify CLOUDFLARE_API_TOKEN is set
if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo >&2 "ERROR: CLOUDFLARE_API_TOKEN environment variable must be set"
  echo >&2 "Get your token at: https://dash.cloudflare.com/profile/api-tokens"
  echo >&2 "Required permissions: Cloudflare Pages:Edit"
  exit 1
fi

# Build wrangler arguments
WRANGLER_ARGS=(
  pages
  deploy
  "${DIST_DIR}"
  --project-name="${PROJECT_NAME}"
  --commit-dirty=true
)

# Add branch if specified
if [[ -n "${BRANCH}" ]]; then
  WRANGLER_ARGS+=(--branch="${BRANCH}")
fi

# Pass through any additional arguments (e.g., --dry-run for testing)
WRANGLER_ARGS+=("$@")

echo "Deploying to Cloudflare Pages project: ${PROJECT_NAME}"
echo "Source directory: ${DIST_DIR}"

exec "${WRANGLER}" "${WRANGLER_ARGS[@]}"
