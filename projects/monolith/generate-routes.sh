#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

MONOLITH_DIR="projects/monolith"
ROUTES_DIR="${MONOLITH_DIR}/frontend/src/routes"

# Clean inner per-service symlinks before regenerating.
# A top-level symlink (e.g. routes/public -> ../../../home/frontend/routes/public)
# means a single service owns the entire namespace — leave it alone.
for visibility in private public; do
	target="${ROUTES_DIR}/${visibility}"
	if [ -L "$target" ]; then
		continue
	fi
	find "$target" -mindepth 1 -type l -delete 2>/dev/null || true
	mkdir -p "$target"
done

# Generate per-service symlinks
for service_dir in "${MONOLITH_DIR}"/*/frontend; do
	service=$(basename "$(dirname "$service_dir")")
	[ "$service" = "frontend" ] && continue # skip the SvelteKit shell itself

	for visibility in private public; do
		target="${ROUTES_DIR}/${visibility}"
		[ -L "$target" ] && continue # namespace owned by another service
		if [ -d "${service_dir}/${visibility}" ]; then
			ln -sf "../../../../${service}/frontend/${visibility}" "${target}/${service}"
		fi
	done
done

# Symlink shared components to $lib
if [ -d "${MONOLITH_DIR}/shared/frontend/components" ]; then
	ln -sf "../../shared/frontend/components" "${ROUTES_DIR}/../lib"
fi
