"""Validates that all sidebar and nav links in VitePress config point to real files.

Prevents drift between the VitePress sidebar/nav configuration and the actual
markdown files assembled into the docs site.
"""

import json
import re
from pathlib import Path

import pytest

# In Bazel's runfiles tree, __file__ mirrors the repo layout:
# {workspace}/projects/websites/docs.jomcgi.dev/config_links_test.py
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
VITEPRESS_DIR = WORKSPACE_ROOT / "projects/websites/docs.jomcgi.dev/.vitepress"
CONFIG_PATH = VITEPRESS_DIR / "config.js"
ADR_SIDEBAR_PATH = VITEPRESS_DIR / "adr-sidebar.json"

# Match link: "/some/path" in config.js (sidebar and nav links)
LINK_PATTERN = re.compile(r'link:\s*"(/[^"]+)"')


def _get_links_from_json(data):
    """Recursively extract all 'link' values from a JSON structure."""
    links = []
    if isinstance(data, dict):
        if "link" in data:
            links.append(data["link"])
        for value in data.values():
            links.extend(_get_links_from_json(value))
    elif isinstance(data, list):
        for item in data:
            links.extend(_get_links_from_json(item))
    return links


def _get_internal_links():
    """Extract all internal links from config.js and generated sidebar JSON."""
    links = []

    # Links from config.js (Architecture sidebar, nav)
    content = CONFIG_PATH.read_text()
    links.extend(
        link for link in LINK_PATTERN.findall(content) if not link.startswith("http")
    )

    # Links from generated ADR sidebar
    if ADR_SIDEBAR_PATH.exists():
        sidebar_data = json.loads(ADR_SIDEBAR_PATH.read_text())
        links.extend(_get_links_from_json(sidebar_data))

    return links


def _link_to_source(link):
    """Map a VitePress sidebar link to its source markdown file.

    The VitePress assembly pipeline:
      docs/BUILD: vitepress_path = "docs"
      VitePress rewrite: docs_rewrite/:rest* -> :rest*

    So sidebar link /docs/services -> source file docs/services.md
    and /docs/decisions/ -> source file docs/decisions/index.md
    """
    url_path = link.lstrip("/")

    if url_path.endswith("/"):
        return WORKSPACE_ROOT / url_path / "index.md"

    md_path = WORKSPACE_ROOT / (url_path + ".md")
    if md_path.exists():
        return md_path

    # Could be a directory with index.md
    index_path = WORKSPACE_ROOT / url_path / "index.md"
    if index_path.exists():
        return index_path

    return md_path  # Return expected path for error reporting


class TestConfigLinks:
    """Verify VitePress config links match actual files."""

    def test_all_sidebar_links_resolve(self):
        """Every link in the sidebar/nav must point to a real markdown file."""
        links = _get_internal_links()
        assert len(links) > 0, "No links found in config — parsing may be broken"

        missing = []
        for link in links:
            source = _link_to_source(link)
            if not source.exists():
                missing.append(f"  {link} -> {source.relative_to(WORKSPACE_ROOT)}")

        assert not missing, "Broken links in VitePress config:\n" + "\n".join(missing)

    def test_all_adrs_in_sidebar(self):
        """Every ADR markdown file should have a corresponding sidebar entry."""
        links = set(_get_internal_links())

        decisions_dir = WORKSPACE_ROOT / "docs/decisions"
        adr_files = sorted(decisions_dir.rglob("*.md"))
        adr_files = [f for f in adr_files if f.name != "index.md"]

        missing = []
        for adr_file in adr_files:
            rel = adr_file.relative_to(WORKSPACE_ROOT)
            # Expected sidebar link: /docs/decisions/agents/001-foo (no .md)
            expected_link = "/" + str(rel).removesuffix(".md")
            if expected_link not in links:
                missing.append(f"  {rel} (expected: {expected_link})")

        assert not missing, "ADR files missing from sidebar:\n" + "\n".join(missing)
