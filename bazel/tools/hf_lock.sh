#!/usr/bin/env bash
# hf_lock.sh - Generate sha256 pins for HuggingFace repository files
#
# This script fetches the file tree from HuggingFace Hub API and outputs
# sha256 checksums for each file, suitable for pinning in MODULE.bazel.
#
# Usage:
#   ./tools/hf_lock.sh <repo_id> [revision]
#
# Examples:
#   ./tools/hf_lock.sh microsoft/phi-2
#   ./tools/hf_lock.sh Qwen/Qwen2.5-0.5B-Instruct main
#   ./tools/hf_lock.sh sentence-transformers/all-MiniLM-L6-v2 refs/pr/123
#
# Output format (MODULE.bazel compatible):
#   HF_MODEL_FILES = {
#       "config.json": "abc123...",
#       "model.safetensors": "def456...",
#   }
#
# For LFS files (large files), the SHA-256 is from the lfs.oid field.
# For regular files, we fetch the file and compute SHA-256.

set -euo pipefail

# Colors for terminal output
if [[ -t 1 ]]; then
	RED='\033[0;31m'
	GREEN='\033[0;32m'
	YELLOW='\033[0;33m'
	BLUE='\033[0;34m'
	NC='\033[0m' # No Color
else
	RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

usage() {
	cat <<EOF
Usage: $(basename "$0") <repo_id> [revision]

Generate sha256 pins for HuggingFace repository files.

Arguments:
    repo_id     HuggingFace repository ID (e.g., "microsoft/phi-2")
    revision    Git revision (default: "main")

Options:
    -h, --help  Show this help message
    -o FILE     Output to file instead of stdout
    -f PATTERN  Filter files by glob pattern (e.g., "*.safetensors")
    --json      Output as JSON instead of Starlark dict
    --quiet     Suppress progress messages

Examples:
    $(basename "$0") microsoft/phi-2
    $(basename "$0") Qwen/Qwen2.5-0.5B-Instruct main -o qwen.lock
    $(basename "$0") sentence-transformers/all-MiniLM-L6-v2 -f "*.safetensors"
EOF
	exit 1
}

# Check dependencies
check_deps() {
	local missing=()
	for cmd in curl jq shasum; do
		if ! command -v "$cmd" &>/dev/null; then
			missing+=("$cmd")
		fi
	done
	if [[ ${#missing[@]} -gt 0 ]]; then
		echo -e "${RED}Error: Missing required commands: ${missing[*]}${NC}" >&2
		exit 1
	fi
}

# Fetch file tree from HuggingFace API
fetch_tree() {
	local repo_id="$1"
	local revision="$2"
	local api_url="https://huggingface.co/api/models/${repo_id}/tree/${revision}"

	local curl_args=(-fsSL)
	if [[ -n "${HF_TOKEN:-}" ]]; then
		curl_args+=(-H "Authorization: Bearer ${HF_TOKEN}")
	fi

	curl "${curl_args[@]}" "$api_url" || {
		echo -e "${RED}Error: Failed to fetch tree from ${api_url}${NC}" >&2
		echo -e "${YELLOW}Hint: For private repos, set HF_TOKEN environment variable${NC}" >&2
		exit 1
	}
}

# Compute SHA-256 for a regular (non-LFS) file
compute_sha256() {
	local repo_id="$1"
	local revision="$2"
	local filepath="$3"
	local url="https://huggingface.co/${repo_id}/resolve/${revision}/${filepath}"

	local curl_args=(-fsSL)
	if [[ -n "${HF_TOKEN:-}" ]]; then
		curl_args+=(-H "Authorization: Bearer ${HF_TOKEN}")
	fi

	local result
	if ! result=$(curl "${curl_args[@]}" "$url" | shasum -a 256 | cut -d' ' -f1); then
		echo -e "${RED}Error: Failed to download or compute SHA-256 for ${filepath}${NC}" >&2
		echo -e "${YELLOW}Hint: Check your network connection or set HF_TOKEN for private repositories${NC}" >&2
		exit 1
	fi
	echo "$result"
}

# Format file size for display
format_size() {
	local size="$1"
	if command -v numfmt >/dev/null 2>&1; then
		numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "${size}B"
	else
		echo "${size}B"
	fi
}

# Main function
main() {
	local output_file=""
	local filter_pattern=""
	local json_output=false
	local quiet=false
	local repo_id=""
	local revision="main"

	# Parse arguments
	while [[ $# -gt 0 ]]; do
		case "$1" in
		-h | --help) usage ;;
		-o)
			shift
			output_file="${1:-}"
			[[ -z "$output_file" ]] && {
				echo "Error: -o requires a filename" >&2
				exit 1
			}
			;;
		-f)
			shift
			filter_pattern="${1:-}"
			[[ -z "$filter_pattern" ]] && {
				echo "Error: -f requires a pattern" >&2
				exit 1
			}
			;;
		--json) json_output=true ;;
		--quiet) quiet=true ;;
		-*)
			echo "Unknown option: $1" >&2
			usage
			;;
		*)
			if [[ -z "$repo_id" ]]; then
				repo_id="$1"
			else
				revision="$1"
			fi
			;;
		esac
		shift
	done

	if [[ -z "$repo_id" ]]; then
		echo -e "${RED}Error: repo_id is required${NC}" >&2
		usage
	fi

	check_deps

	# Fetch tree
	[[ "$quiet" == false ]] && echo -e "${BLUE}Fetching file tree for ${repo_id}@${revision}...${NC}" >&2
	local tree
	tree=$(fetch_tree "$repo_id" "$revision")

	# Parse files and compute hashes
	local files=()
	local hashes=()

	# Declare variables used in while loop
	local path type lfs_oid size sha256 human_readable_size

	while IFS= read -r line; do
		path=$(echo "$line" | jq -r '.path')
		type=$(echo "$line" | jq -r '.type')
		lfs_oid=$(echo "$line" | jq -r '.lfs.oid // empty')
		size=$(echo "$line" | jq -r '.size // 0')

		# Skip directories
		[[ "$type" != "file" ]] && continue

		# Apply filter if specified
		if [[ -n "$filter_pattern" ]]; then
			# shellcheck disable=SC2053
			[[ "$path" != $filter_pattern ]] && continue
		fi

		sha256=""
		if [[ -n "$lfs_oid" ]]; then
			# LFS file - use the lfs.oid directly (it's already SHA-256)
			sha256="$lfs_oid"
			if [[ "$quiet" == false ]]; then
				human_readable_size=$(format_size "$size")
				echo -e "${GREEN}[LFS]${NC} $path (${human_readable_size})" >&2
			fi
		else
			# Regular file - need to fetch and compute
			[[ "$quiet" == false ]] && echo -e "${YELLOW}[GET]${NC} $path (computing sha256...)" >&2
			sha256=$(compute_sha256 "$repo_id" "$revision" "$path")
		fi

		files+=("$path")
		hashes+=("$sha256")
	done < <(echo "$tree" | jq -c '.[]')

	# Generate output
	local output=""
	if [[ "$json_output" == true ]]; then
		# JSON output
		output="{\n"
		for i in "${!files[@]}"; do
			local comma=""
			[[ $i -lt $((${#files[@]} - 1)) ]] && comma=","
			output+="  \"${files[$i]}\": \"${hashes[$i]}\"${comma}\n"
		done
		output+="}"
	else
		# Starlark dict output (for MODULE.bazel)
		local var_name base_name
		base_name=$(echo "${repo_id##*/}" |
			tr '[:lower:]' '[:upper:]' |
			sed 's/[^A-Z0-9_]/_/g' |
			sed 's/_\{2,\}/_/g')
		# Ensure variable name doesn't start with a digit
		if [[ "$base_name" =~ ^[0-9] ]]; then
			base_name="_${base_name}"
		fi
		var_name="${base_name}_FILES"

		output="# Generated by hf_lock.sh for ${repo_id}@${revision}\n"
		output+="# $(date -u +"%Y-%m-%dT%H:%M:%SZ")\n"
		output+="${var_name} = {\n"
		for i in "${!files[@]}"; do
			local comma=""
			[[ $i -lt $((${#files[@]} - 1)) ]] && comma=","
			output+="    \"${files[$i]}\": \"${hashes[$i]}\"${comma}\n"
		done
		output+="}"
	fi

	# Write output
	if [[ -n "$output_file" ]]; then
		echo -e "$output" >"$output_file"
		[[ "$quiet" == false ]] && echo -e "${GREEN}Written to ${output_file}${NC}" >&2
	else
		echo -e "$output"
	fi

	if [[ "$quiet" == false ]]; then
		echo -e "${GREEN}Done! Processed ${#files[@]} files${NC}" >&2
	fi
}

main "$@"
