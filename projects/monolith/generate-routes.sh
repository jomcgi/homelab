#!/usr/bin/env bash
set -euo pipefail

MONOLITH_DIR="projects/monolith"
ROUTES_DIR="${MONOLITH_DIR}/frontend/src/routes"

# Clean existing symlinks in routes dir
find "${ROUTES_DIR}/private" "${ROUTES_DIR}/public" -type l -delete 2>/dev/null || true
mkdir -p "${ROUTES_DIR}/private" "${ROUTES_DIR}/public"

# Generate symlinks for each service
for service_dir in "${MONOLITH_DIR}"/*/frontend; do
	service=$(basename "$(dirname "$service_dir")")
	[ "$service" = "frontend" ] && continue # skip the SvelteKit shell itself

	for visibility in private public; do
		if [ -d "${service_dir}/${visibility}" ]; then
			ln -sf "../../../../${service}/frontend/${visibility}" "${ROUTES_DIR}/${visibility}/${service}"
		fi
	done
done

# Symlink shared components to $lib
if [ -d "${MONOLITH_DIR}/shared/frontend/components" ]; then
	ln -sf "../../shared/frontend/components" "${ROUTES_DIR}/../lib"
fi
