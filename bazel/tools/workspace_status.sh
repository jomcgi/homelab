#!/usr/bin/env bash
# Produces space-separated key-values for stamp variables.
# Those starting with "STABLE_" will cause actions to re-run when they change.
# See https://docs.aspect.build/rulesets/aspect_bazel_lib/docs/stamping/
set -o errexit -o nounset -o pipefail

git_commit=$(git rev-parse HEAD)
git_short_sha=$(git rev-parse --short HEAD)

# Follows https://blog.aspect.build/versioning-releases-from-a-monorepo
auto_version=$(
	git describe --tags --long --match="[0-9][0-9][0-9][0-9].[0-9][0-9]" 2>/dev/null |
		sed -e 's/-/./;s/-g/-/' || echo "0.0.0"
)

# Generate timestamp-based image tag: YYYY.MM.DD.HH.MM.SS-shortsha
base_image_tag=$(date -u +"%Y.%m.%d.%H.%M.%S")-${git_short_sha}

# Get branch name (sanitized for Docker tags)
# Check multiple CI environment variables for branch name
if [ -n "${GITHUB_REF_NAME:-}" ]; then
	# GitHub Actions provides this directly
	branch="${GITHUB_REF_NAME}"
elif [ -n "${GIT_BRANCH:-}" ]; then
	# BuildBuddy and Jenkins provide this
	branch="${GIT_BRANCH}"
elif [ -n "${GITHUB_REF:-}" ]; then
	# GitHub webhook events provide refs/heads/branch-name
	# Extract branch name from refs/heads/ or refs/pull/
	if [[ "${GITHUB_REF}" == refs/heads/* ]]; then
		branch="${GITHUB_REF#refs/heads/}"
	elif [[ "${GITHUB_REF}" == refs/pull/* ]]; then
		# For pull requests, use PR branch name if available
		branch="${GITHUB_HEAD_REF:-pr-${GITHUB_REF#refs/pull/}}"
	else
		branch="${GITHUB_REF}"
	fi
elif [ -n "${BUILDKITE_BRANCH:-}" ]; then
	# Buildkite CI
	branch="${BUILDKITE_BRANCH}"
elif [ -n "${CIRCLE_BRANCH:-}" ]; then
	# CircleCI
	branch="${CIRCLE_BRANCH}"
elif [ -n "${CI_COMMIT_BRANCH:-}" ]; then
	# GitLab CI
	branch="${CI_COMMIT_BRANCH}"
else
	# Fallback to git command (may fail in detached HEAD state)
	branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
fi

# Safety check: if env says "main" but HEAD isn't actually origin/main,
# we're in a PR build where the CI set GIT_BRANCH to the target branch.
# Fall back to a commit-derived tag to avoid overwriting the "main" image.
if [ "${branch}" = "main" ]; then
	main_sha=$(git rev-parse origin/main 2>/dev/null || echo "")
	if [ -n "$main_sha" ] && [ "$git_commit" != "$main_sha" ]; then
		branch="pr-${git_short_sha}"
		>&2 echo "workspace_status.sh: HEAD (${git_short_sha}) != origin/main, using branch='${branch}'"
	fi
fi

# Debug output when CI is set (only visible in build logs)
if [ "${CI:-}" = "true" ] || [ "${CI:-}" = "1" ]; then
	>&2 echo "workspace_status.sh: Detected branch '${branch}' from environment"
	>&2 echo "  GITHUB_REF_NAME=${GITHUB_REF_NAME:-<not set>}"
	>&2 echo "  GIT_BRANCH=${GIT_BRANCH:-<not set>}"
	>&2 echo "  GITHUB_REF=${GITHUB_REF:-<not set>}"
fi
# Sanitize: replace / with - and convert to lowercase
branch_tag=$(echo "${branch}" | tr '/' '-' | tr '[:upper:]' '[:lower:]')

# Add dev- prefix for non-main branches (for ArgoCD Image Updater filtering)
if [ "${branch}" = "main" ]; then
	image_tag="${base_image_tag}"
else
	image_tag="dev-${base_image_tag}"
fi

cat <<EOF
STABLE_GIT_COMMIT ${git_commit}
STABLE_MONOREPO_VERSION ${auto_version}
STABLE_IMAGE_TAG ${image_tag}
STABLE_BRANCH_TAG ${branch_tag}
EOF
