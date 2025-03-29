#!/bin/bash

# --- Configuration ---
SOURCE_DIR="services/obsidian/repo"      # Directory containing markdown files
OUTPUT_FILE="services/obsidian/all_markdown_content.txt" # Name of the output file
SEPARATOR_TEMPLATE="\n\n--- Content From: %s ---\n\n" # Separator template (printf format)

# --- Script ---

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: Source directory '$SOURCE_DIR' not found."
  exit 1
fi

# Ensure the output file is empty before starting
> "$OUTPUT_FILE"

echo "Finding and concatenating .md files from '$SOURCE_DIR'..."

# Find all files ending in .md (case-insensitive), print null-separated
# Pipe to xargs -0 to handle any filename characters safely
# For each file, execute sh -c '...'
find "$SOURCE_DIR" -type f -iname "*.md" -print0 | \
  xargs -0 -I {} sh -c \
    'printf "$1" "$2"; cat "$2"' -- "$SEPARATOR_TEMPLATE" {} >> "$OUTPUT_FILE"

# Optional: Remove the very first separator if the file isn't empty
if [ -s "$OUTPUT_FILE" ]; then
  # Calculate separator length (approximation, works for simple templates)
  # More robustly, capture the first separator exactly:
  first_separator=$(printf "$SEPARATOR_TEMPLATE" "$(find "$SOURCE_DIR" -type f -iname "*.md" -print -quit)")
  if [[ -n "$first_separator" ]]; then # Check if a file was found
    sed -i "1s|^$(printf "%q" "$first_separator")||" "$OUTPUT_FILE" # Use sed -i to edit in-place
    # Note: %q in printf might not be available in older bash/printf. Adjust if needed.
    # Basic alternative (less safe for complex separators): sed -i '1s/^--- Content From:.*---//' "$OUTPUT_FILE"
  fi
fi


echo "Concatenation complete. Output written to '$OUTPUT_FILE'."