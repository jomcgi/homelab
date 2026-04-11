# Tests for python-shadow-module-import rule.
# Positive cases have `# ruleid:` on the line before the shadowing assignment.
# Negative cases have `# ok:` on the line before.

from knowledge import links, wikilinks
import os
import re

# --- Violations (should be flagged) ---


def bad_shadow_from_import():
    body = "[[some-note]]"
    # ruleid: python-shadow-module-import
    wikilinks = links.extract(body)
    return wikilinks


def bad_shadow_bare_import():
    # ruleid: python-shadow-module-import
    os = "/tmp/workdir"
    return os


class Reconciler:
    async def upsert_note(self, body: str):
        # ruleid: python-shadow-module-import
        wikilinks = links.extract(body)
        return wikilinks

    def compile_pattern(self, pattern: str):
        # ruleid: python-shadow-module-import
        re = pattern + r"\w+"
        return re


# --- OK cases (should not be flagged) ---


def ok_renamed_variable():
    body = "[[some-note]]"
    # ok: note_links has a different name than the wikilinks module
    note_links = wikilinks.extract(body)
    return note_links


def ok_uses_module_not_reassigned():
    # ok: os is used but not reassigned
    return os.path.join("/tmp", "file.txt")


def ok_augmented_assignment():
    items = []
    # ok: augmented assignment appends to a list, not shadowing the module
    items += [1, 2, 3]
    return items


def ok_unrelated_name():
    # ok: `path` is not an imported module name
    path = "/tmp/file.txt"
    return path
