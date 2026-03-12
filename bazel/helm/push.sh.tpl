#!/usr/bin/env bash
# Push a packaged Helm chart to an OCI registry
# Template substitutions: {{HELM}}, {{CHART_TGZ}}, {{REPOSITORY}}, {{CHART_VERSION_SH}}, {{CHART_DIR}}

set -o errexit -o nounset -o pipefail

# Bazel runfiles setup
RUNFILES_DIR="${RUNFILES_DIR:-}"
if [[ -z "$RUNFILES_DIR" ]]; then
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

readonly HELM="$(rlocation "{{HELM}}")"
readonly CHART_TGZ="$(rlocation "{{CHART_TGZ}}")"
REPOSITORY="{{REPOSITORY}}"
CHART_VERSION_SH="{{CHART_VERSION_SH}}"
CHART_DIR="{{CHART_DIR}}"

# Resolve chart-version.sh via rlocation if it's a runfiles path
if [[ -n "$CHART_VERSION_SH" ]] && ! [[ -x "$CHART_VERSION_SH" ]]; then
  CHART_VERSION_SH="$(rlocation "$CHART_VERSION_SH" 2>/dev/null || echo "")"
fi

# Parse command line args
while (( $# > 0 )); do
  case $1 in
    (-r|--repository)
      REPOSITORY="$2"
      shift 2;;
    (--repository=*)
      REPOSITORY="${1#--repository=}"
      shift;;
    (*)
      echo "Unknown argument: $1" >&2
      exit 1;;
  esac
done

# --- Compute next version ---
PUSH_TGZ="$CHART_TGZ"
CURRENT_VERSION=""
NEW_VERSION=""

if [[ -n "$CHART_VERSION_SH" ]] && [[ -n "$CHART_DIR" ]] && [[ -x "$CHART_VERSION_SH" ]]; then
  # Derive Bazel package from chart dir for dependency query
  BAZEL_PKG="//${CHART_DIR}:chart.package"
  CURRENT_VERSION=$(grep '^version:' "${CHART_DIR}/Chart.yaml" | head -1 | awk '{print $2}' | tr -d '"')
  NEW_VERSION=$("$CHART_VERSION_SH" "$CHART_DIR" "$BAZEL_PKG")

  if [[ "$NEW_VERSION" != "$CURRENT_VERSION" ]]; then
    echo "Chart version bump: ${CURRENT_VERSION} -> ${NEW_VERSION}"

    # Re-package with new version
    WORK_DIR=$(mktemp -d)
    tar -xzf "$CHART_TGZ" -C "$WORK_DIR"
    CHART_NAME=$(ls "$WORK_DIR")
    sed "s/^version:.*/version: ${NEW_VERSION}/" "$WORK_DIR/$CHART_NAME/Chart.yaml" > "$WORK_DIR/$CHART_NAME/Chart.yaml.tmp"
    mv "$WORK_DIR/$CHART_NAME/Chart.yaml.tmp" "$WORK_DIR/$CHART_NAME/Chart.yaml"
    PUSH_TGZ="$WORK_DIR/${CHART_NAME}-${NEW_VERSION}.tgz"
    "$HELM" package "$WORK_DIR/$CHART_NAME" --destination "$WORK_DIR"

    trap "rm -rf '$WORK_DIR'" EXIT
  else
    echo "Chart version unchanged at ${CURRENT_VERSION}"
  fi
fi

echo "Pushing Helm chart: ${PUSH_TGZ}"
echo "  Repository: ${REPOSITORY}"

"${HELM}" push "${PUSH_TGZ}" "${REPOSITORY}"

echo "Successfully pushed chart to ${REPOSITORY}"

# --- Commit version bump back to git ---
if [[ -n "${NEW_VERSION}" ]] && [[ "${NEW_VERSION}" != "${CURRENT_VERSION}" ]]; then
  CHART_YAML="${CHART_DIR}/Chart.yaml"
  if [[ -f "$CHART_YAML" ]]; then
    echo "Committing version bump to ${CHART_YAML}..."
    sed "s/^version:.*/version: ${NEW_VERSION}/" "$CHART_YAML" > "${CHART_YAML}.tmp"
    mv "${CHART_YAML}.tmp" "$CHART_YAML"

    CHART_NAME_LOWER=$(grep '^name:' "$CHART_YAML" | head -1 | awk '{print $2}' | tr -d '"')
    git config user.name "chart-version-bot"
    git config user.email "chart-version-bot@users.noreply.github.com"
    git add "$CHART_YAML"
    git commit -m "chore(${CHART_NAME_LOWER}): bump chart version to ${NEW_VERSION}"
    git push origin HEAD:main
    echo "Version bump committed and pushed"
  fi
fi
