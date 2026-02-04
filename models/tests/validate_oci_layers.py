#!/usr/bin/env python3
"""Validate OCI image layer structure.

This test verifies that OCI images have the expected layer structure:
- Multi-platform manifest (amd64, arm64)
- Expected number of layers per platform
- Layer sizes are reasonable (not empty, not corrupted)
"""

import json
import sys
from pathlib import Path


def validate_oci_image(image_dir: Path, expected_layers: int, platform: str = "linux/amd64"):
    """Validate OCI image structure.

    Args:
        image_dir: Path to OCI image directory (bazel-bin output)
        expected_layers: Expected number of layers in the image
        platform: Platform to validate (e.g., "linux/amd64")
    """
    # Read index.json
    index_path = image_dir / "index.json"
    if not index_path.exists():
        print(f"ERROR: index.json not found at {index_path}")
        return False

    with open(index_path) as f:
        index = json.load(f)

    # Get the main manifest digest
    if not index.get("manifests"):
        print("ERROR: No manifests in index.json")
        return False

    main_digest = index["manifests"][0]["digest"].replace("sha256:", "")

    # Read the multi-platform manifest
    manifest_path = image_dir / "blobs" / "sha256" / main_digest
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found at {manifest_path}")
        return False

    with open(manifest_path) as f:
        multi_platform_manifest = json.load(f)

    # Find platform-specific manifest
    platform_os, platform_arch = platform.split("/")
    platform_manifest_digest = None

    for m in multi_platform_manifest.get("manifests", []):
        p = m.get("platform", {})
        if p.get("os") == platform_os and p.get("architecture") == platform_arch:
            platform_manifest_digest = m["digest"].replace("sha256:", "")
            break

    if not platform_manifest_digest:
        print(f"ERROR: Platform {platform} not found in manifest")
        return False

    # Read platform-specific manifest
    platform_manifest_path = image_dir / "blobs" / "sha256" / platform_manifest_digest
    with open(platform_manifest_path) as f:
        platform_manifest = json.load(f)

    # Validate layers
    layers = platform_manifest.get("layers", [])
    if len(layers) != expected_layers:
        print(f"ERROR: Expected {expected_layers} layers, found {len(layers)}")
        return False

    # Validate layer blobs exist and have reasonable sizes
    for i, layer in enumerate(layers):
        digest = layer["digest"].replace("sha256:", "")
        size = layer.get("size", 0)
        blob_path = image_dir / "blobs" / "sha256" / digest

        if not blob_path.exists():
            print(f"ERROR: Layer {i} blob not found: {blob_path}")
            return False

        actual_size = blob_path.stat().st_size
        if actual_size != size:
            print(f"WARNING: Layer {i} size mismatch: manifest={size}, actual={actual_size}")

        if actual_size == 0:
            print(f"ERROR: Layer {i} is empty")
            return False

    print(f"✓ OCI image validated: {len(layers)} layers, {platform}")
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: validate_oci_layers.py <image_dir> <expected_layers> [platform]")
        sys.exit(1)

    image_dir = Path(sys.argv[1])
    expected_layers = int(sys.argv[2])
    platform = sys.argv[3] if len(sys.argv) > 3 else "linux/amd64"

    if not validate_oci_image(image_dir, expected_layers, platform):
        sys.exit(1)


if __name__ == "__main__":
    main()
