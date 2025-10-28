#!/usr/bin/env bash
# Auto-generate the push_all_images multirun target from discovered oci_push targets
set -euo pipefail

BUILD_FILE="BUILD"
MARKER_START="# BEGIN AUTO-GENERATED: push_all_images"
MARKER_END="# END AUTO-GENERATED: push_all_images"

echo "🔍 Discovering all oci_push targets..."
PUSH_TARGETS=$(bazel query 'kind("oci_push", //...)' --output label 2>/dev/null | sort)

if [ -z "$PUSH_TARGETS" ]; then
  echo "⚠️  No oci_push targets found"
  exit 0
fi

echo "📦 Found $(echo "$PUSH_TARGETS" | wc -l) image(s)"

# Generate the multirun target
MULTIRUN_CONTENT="$MARKER_START
load(\"@rules_multirun//:defs.bzl\", \"multirun\")

multirun(
    name = \"push_all_images\",
    commands = ["

# Add each target as a command
while IFS= read -r target; do
  MULTIRUN_CONTENT="$MULTIRUN_CONTENT
        \"$target\","
done <<< "$PUSH_TARGETS"

MULTIRUN_CONTENT="$MULTIRUN_CONTENT
    ],
    jobs = 0,  # 0 means unlimited parallelism
)
$MARKER_END"

# Update BUILD file
if grep -q "$MARKER_START" "$BUILD_FILE"; then
  # Replace existing block
  awk -v new="$MULTIRUN_CONTENT" '
    BEGIN { skip=0 }
    /# BEGIN AUTO-GENERATED: push_all_images/ { print new; skip=1; next }
    /# END AUTO-GENERATED: push_all_images/ { skip=0; next }
    !skip { print }
  ' "$BUILD_FILE" > "$BUILD_FILE.tmp"
  mv "$BUILD_FILE.tmp" "$BUILD_FILE"
  echo "✅ Updated push_all_images in BUILD"
else
  # Append new block
  echo "" >> "$BUILD_FILE"
  echo "$MULTIRUN_CONTENT" >> "$BUILD_FILE"
  echo "✅ Added push_all_images to BUILD"
fi
