"""Public API for rules_wrangler - Bazel rules for Cloudflare Pages deployment."""

load("//rules_wrangler:pages.bzl", _wrangler_pages = "wrangler_pages")

# Re-export all public symbols
wrangler_pages = _wrangler_pages
