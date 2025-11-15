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
# In CI: use GITHUB_REF_NAME, otherwise use git
if [ -n "${GITHUB_REF_NAME:-}" ]; then
	branch="${GITHUB_REF_NAME}"
else
	branch=$(git rev-parse --abbrev-ref HEAD)
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
