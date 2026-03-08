#!/usr/bin/env bash
# verify-py3-image.sh — Verify Python OCI image has correct runtime configuration.
#
# Inspects the OCI image config blob to ensure PYTHONPATH, RUNFILES_DIR, and
# entrypoint are set. This catches packaging regressions where py_venv_binary
# images ship without the environment needed to locate Python modules.
#
# Usage: verify-py3-image.sh <image_dir>
set -euo pipefail

IMAGE_DIR="$1"

if [ ! -d "$IMAGE_DIR" ]; then
	echo "FAIL: Image directory not found: $IMAGE_DIR" >&2
	exit 1
fi

exec python3 -c '
import json, os, sys

image_dir = sys.argv[1]

# Walk the OCI layout: index.json -> manifest -> config
with open(os.path.join(image_dir, "index.json")) as f:
    index = json.load(f)

manifest_ref = index["manifests"][0]["digest"]
algo, digest = manifest_ref.split(":", 1)
with open(os.path.join(image_dir, "blobs", algo, digest)) as f:
    manifest = json.load(f)

config_ref = manifest["config"]["digest"]
algo, digest = config_ref.split(":", 1)
with open(os.path.join(image_dir, "blobs", algo, digest)) as f:
    config = json.load(f)

container = config.get("config", {})
env_list = container.get("Env", [])
entrypoint = container.get("Entrypoint", [])
env = dict(e.split("=", 1) for e in env_list)

errors = []

if "PYTHONPATH" not in env:
    errors.append("PYTHONPATH not set in image environment")
elif not env["PYTHONPATH"]:
    errors.append("PYTHONPATH is empty")

if "RUNFILES_DIR" not in env:
    errors.append("RUNFILES_DIR not set in image environment")

if not entrypoint:
    errors.append("No entrypoint configured")

if errors:
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)

print("PASS: entrypoint=" + str(entrypoint))
print("PASS: PYTHONPATH=" + env["PYTHONPATH"])
print("PASS: RUNFILES_DIR=" + env["RUNFILES_DIR"])
' "$IMAGE_DIR"
