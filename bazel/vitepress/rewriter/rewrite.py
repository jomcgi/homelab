"""Link rewriter for VitePress documentation site.

Processes assembled markdown files to resolve, remap, and validate
relative links so they work correctly on the docs site while preserving
the original links for GitHub rendering.

Three-step pipeline per link:
1. Resolve: relative path -> full repo path
2. Remap: repo path -> vitepress path via path map
3. Validate: check target file exists in assembled tree

Links to files outside the docs site are stripped (display text preserved,
link markup removed) with a build warning.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Match markdown links: [text](url)
# Exclude images (![...](...)  and external URLs (http://, https://)
LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")


def resolve_link(link_target, file_repo_path):
    """Resolve a relative link target against the file's repo path.

    Args:
        link_target: The raw link target from markdown (e.g., "../services/foo/README.md")
        file_repo_path: The repo-relative directory of the file containing the link

    Returns:
        Resolved repo-relative path, or None if the link is external/anchor-only
    """
    # Skip external URLs and anchors
    if link_target.startswith(("http://", "https://", "mailto:", "#")):
        return None

    # Strip anchor fragments for resolution (preserve for output)
    target_without_anchor = link_target.split("#")[0]
    if not target_without_anchor:
        return None

    # Resolve relative to the file's directory
    resolved = os.path.normpath(os.path.join(file_repo_path, target_without_anchor))

    # Normalise to forward slashes
    resolved = resolved.replace("\\", "/")

    # Remove leading ./ if present
    if resolved.startswith("./"):
        resolved = resolved[2:]

    return resolved


def remap_link(resolved_path, path_map):
    """Remap a resolved repo path to its vitepress path.

    Tries to find the longest matching prefix in the path map.

    Args:
        resolved_path: Full repo-relative path (e.g., "services/ships_api/README.md")
        path_map: Dict mapping repo_path -> vitepress_path

    Returns:
        Remapped vitepress path, or None if no mapping found
    """
    # Try progressively shorter prefixes
    parts = resolved_path.split("/")
    for i in range(len(parts), 0, -1):
        prefix = "/".join(parts[:i])
        if prefix in path_map:
            vitepress_prefix = path_map[prefix]
            remainder = "/".join(parts[i:])
            if remainder:
                return f"{vitepress_prefix}/{remainder}"
            return vitepress_prefix

    return None


def rewrite_file(content, file_repo_path, path_map, assembled_root):
    """Rewrite all markdown links in a file's content.

    Args:
        content: The markdown file content
        file_repo_path: Repo-relative directory path of this file
        path_map: Dict mapping repo_path -> vitepress_path
        assembled_root: Path to the assembled content tree for validation

    Returns:
        Tuple of (rewritten_content, list of warning messages)
    """
    warnings = []

    def replace_link(match):
        display_text = match.group(1)
        link_target = match.group(2)

        # Preserve anchor fragment
        anchor = ""
        if "#" in link_target:
            _, anchor = link_target.split("#", 1)
            anchor = "#" + anchor

        # Step 1: Resolve
        resolved = resolve_link(link_target, file_repo_path)
        if resolved is None:
            # External or anchor-only link — pass through unchanged
            return match.group(0)

        # Step 2: Remap
        remapped = remap_link(resolved, path_map)
        if remapped is None:
            warnings.append(f"link to {resolved} stripped (not in docs site)")
            return display_text  # Strip link, keep text

        # Step 3: Validate — check file exists in assembled tree
        check_path = os.path.join(assembled_root, remapped)
        if not os.path.exists(check_path):
            warnings.append(
                f"link to {resolved} stripped (file not found at {remapped})"
            )
            return display_text

        # Build the final link with absolute path
        final_target = f"/{remapped}{anchor}"
        return f"[{display_text}]({final_target})"

    rewritten = LINK_PATTERN.sub(replace_link, content)
    return rewritten, warnings


def main():
    parser = argparse.ArgumentParser(description="Rewrite markdown links for VitePress")
    parser.add_argument(
        "--content-dir", required=True, help="Path to assembled content directory"
    )
    parser.add_argument("--path-map", required=True, help="Path to JSON path map file")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Path to output directory for rewritten files",
    )
    args = parser.parse_args()

    with open(args.path_map) as f:
        path_map = json.load(f)

    content_dir = Path(args.content_dir)
    output_dir = Path(args.output_dir)
    total_warnings = 0

    for md_file in content_dir.rglob("*.md"):
        rel_path = md_file.relative_to(content_dir)
        file_repo_dir = str(rel_path.parent)
        if file_repo_dir == ".":
            file_repo_dir = ""

        content = md_file.read_text(encoding="utf-8")
        rewritten, warnings = rewrite_file(
            content,
            file_repo_dir,
            path_map,
            str(content_dir),
        )

        for w in warnings:
            print(f"WARNING: {rel_path}:{w}", file=sys.stderr)
            total_warnings += 1

        out_path = output_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rewritten, encoding="utf-8")

    if total_warnings > 0:
        print(f"\n{total_warnings} link(s) stripped during rewrite", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
