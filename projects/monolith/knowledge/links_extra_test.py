"""Additional coverage for wikilink extraction edge cases.

Complements links_test.py by covering behaviors that were not previously
exercised:

1. Unclosed fenced code blocks — the `_FENCED` regex requires a matched
   closing ` ``` ` to strip code; an unclosed fence leaves the wikilinks
   inside the "code block" visible to the extractor. This is documented
   current behaviour so that any future change (e.g. also stripping from
   unclosed fences) is an intentional breaking change, not a silent regression.

2. Adjacent/consecutive wikilinks with no space between them.
3. Link target that is all whitespace after stripping anchors.
"""

from knowledge.links import Link, extract


class TestUnclosedFencedBlock:
    """Links inside unclosed fenced code blocks are NOT filtered.

    The `_FENCED` regex is ``re.compile(r"```.*?```", re.DOTALL)`` — it
    requires a matched closing backtick-triple. An opening ``` that is never
    closed means the regex does not match and the text between the fence open
    and end-of-string is left intact for the wikilink pass to process.

    This test documents the current (intentional) behaviour so regressions
    are surfaced explicitly.
    """

    def test_link_inside_unclosed_fence_is_extracted(self):
        """A wikilink after an unclosed ``` is NOT stripped and therefore
        appears in the output.

        The fence pattern requires paired backtick-triples; a lone opening
        fence without a matching close does not qualify.
        """
        body = "```\n[[InsideUnclosedFence]]\n"
        # There is no closing ```, so _FENCED does not match and the link is
        # NOT stripped. The extractor finds it.
        result = extract(body)
        assert result == [Link(target="InsideUnclosedFence", display=None)]

    def test_links_outside_closed_fence_still_work_with_unclosed(self):
        """A closed fence earlier in the document strips its content normally;
        an unclosed fence later does not affect links already processed.
        """
        body = (
            "[[BeforeFence]]\n"
            "```\n[[InsideClosed]]\n```\n"
            "[[AfterClosedFence]]\n"
            "```\n[[InsideUnclosed]]\n"
        )
        targets = [link.target for link in extract(body)]
        # Closed fence strips [[InsideClosed]].
        assert "InsideClosed" not in targets
        # Links outside fences are found.
        assert "BeforeFence" in targets
        assert "AfterClosedFence" in targets
        # Unclosed fence does NOT strip [[InsideUnclosed]].
        assert "InsideUnclosed" in targets

    def test_fully_closed_fence_still_strips(self):
        """Control: a properly closed fence DOES strip its contents.

        This confirms that the test above is meaningfully exercising the
        unclosed-fence code path rather than a broken extractor.
        """
        body = "Real [[Outside]]\n```\n[[Inside]]\n```\n"
        targets = [link.target for link in extract(body)]
        assert "Outside" in targets
        assert "Inside" not in targets


class TestConsecutiveWikilinks:
    """Edge cases with wikilinks that appear immediately adjacent."""

    def test_wikilinks_separated_only_by_whitespace(self):
        """Two wikilinks with only whitespace between them are both extracted."""
        body = "[[Alpha]]   [[Beta]]"
        targets = [link.target for link in extract(body)]
        assert targets == ["Alpha", "Beta"]

    def test_wikilinks_with_no_separator(self):
        """Two wikilinks with no whitespace between closing and opening brackets."""
        body = "[[Foo]][[Bar]]"
        targets = [link.target for link in extract(body)]
        assert targets == ["Foo", "Bar"]


class TestWhitespaceOnlyTarget:
    """Links whose target reduces to empty/whitespace are silently dropped."""

    def test_link_with_only_spaces_as_target_is_dropped(self):
        """A wikilink containing only spaces has no meaningful target.

        After `target.strip()` produces an empty string the extractor's
        `if not target` guard drops the link.
        """
        # The regex requires at least one non-bracket character, but a
        # string of spaces satisfies that; stripping then yields "".
        body = "[[   ]]"
        assert extract(body) == []

    def test_anchor_after_spaces_produces_empty_target(self):
        """[[   #section]] strips the anchor and the remaining spaces produce
        an empty target — the link is dropped.
        """
        body = "[[   #section]] is nothing"
        assert extract(body) == []
