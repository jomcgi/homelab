"""Tests for gap_unlinkify — replace [[X]] with bare text where slug(X) matches."""

from __future__ import annotations

from knowledge.gap_unlinkify import unlinkify, unlinkify_if_changed


def test_bare_link_replaced_with_target_text():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, {"bayes-theorem"}) == "We use Bayes' Theorem heavily."


def test_aliased_link_replaced_with_display_text():
    body = "We use [[Bayes' Theorem|Bayes]] heavily."
    assert unlinkify(body, {"bayes-theorem"}) == "We use Bayes heavily."


def test_heading_anchor_dropped_in_replacement():
    body = "See [[Bayes' Theorem#Derivation]] for details."
    assert unlinkify(body, {"bayes-theorem"}) == "See Bayes' Theorem for details."


def test_block_anchor_dropped_in_replacement():
    body = "See [[Note^para1]] above."
    assert unlinkify(body, {"note"}) == "See Note above."


def test_unrelated_wikilinks_preserved():
    body = "We use [[Bayes' Theorem]] not [[Frequentism]]."
    assert (
        unlinkify(body, {"bayes-theorem"})
        == "We use Bayes' Theorem not [[Frequentism]]."
    )


def test_fenced_code_block_left_untouched():
    body = "Prose [[Foo]] here.\n\n```\ncode [[Foo]] inside\n```\n"
    out = unlinkify(body, {"foo"})
    assert "Prose Foo here." in out
    assert "code [[Foo]] inside" in out  # fenced — preserved


def test_inline_code_left_untouched():
    body = "Prose [[Foo]] but `inline [[Foo]]` stays."
    out = unlinkify(body, {"foo"})
    assert "Prose Foo but" in out
    assert "`inline [[Foo]]`" in out


def test_no_match_returns_input_unchanged():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, {"frequentism"}) == body


def test_empty_slugs_set_is_no_op():
    body = "We use [[Bayes' Theorem]] heavily."
    assert unlinkify(body, set()) == body


def test_repeated_link_all_replaced():
    body = "[[Foo]] then [[Foo]] then [[Foo|foo]]."
    assert unlinkify(body, {"foo"}) == "Foo then Foo then foo."


def test_unlinkify_if_changed_returns_none_on_noop():
    body = "Plain prose, no links."
    assert unlinkify_if_changed(body, {"foo"}) is None


def test_unlinkify_if_changed_returns_body_when_changed():
    body = "We use [[Foo]] daily."
    assert unlinkify_if_changed(body, {"foo"}) == "We use Foo daily."


def test_slugify_matches_gardener():
    """Local _slugify must match gardener._slugify byte-for-byte."""
    from knowledge.gap_unlinkify import _slugify as ours
    from knowledge.gardener import _slugify as theirs

    for s in ["Bayes' Theorem", "Foo Bar", "Already-Slug", "  Mixed/Case! "]:
        assert ours(s) == theirs(s), f"divergence on {s!r}"


def test_link_inside_fence_does_not_consume_outer_link():
    """Span detection must be precise: a [[Foo]] before a fence containing [[Foo]]
    must still be replaced, while the fenced one stays intact."""
    body = "Outer [[Foo]].\n\n```\nFenced [[Foo]] stays.\n```\n\nAfter [[Foo]]."
    out = unlinkify(body, {"foo"})
    assert "Outer Foo." in out
    assert "Fenced [[Foo]] stays." in out
    assert "After Foo." in out
