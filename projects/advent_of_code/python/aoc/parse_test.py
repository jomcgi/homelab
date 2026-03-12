"""Tests for aoc.parse module."""

import pytest

from projects.advent_of_code.python.aoc.parse import (
    chars,
    floats,
    ints,
    lines,
    paragraphs,
    words,
)


# --- lines ---

def test_lines_basic():
    assert lines("a\nb\nc") == ["a", "b", "c"]


def test_lines_trailing_newline():
    assert lines("a\nb\n") == ["a", "b"]


def test_lines_empty():
    assert lines("") == []
    assert lines("\n") == []


def test_lines_single():
    assert lines("hello") == ["hello"]


# --- paragraphs ---

def test_paragraphs_basic():
    result = paragraphs("a\nb\n\nc\nd")
    assert result == ["a\nb", "c\nd"]


def test_paragraphs_empty():
    assert paragraphs("") == []
    assert paragraphs("   \n   ") == []


def test_paragraphs_single():
    assert paragraphs("only one paragraph") == ["only one paragraph"]


# --- ints ---

def test_ints_positives():
    assert ints("1 2 3") == [1, 2, 3]


def test_ints_negatives():
    assert ints("-1 -2 -3") == [-1, -2, -3]


def test_ints_mixed():
    assert ints("foo 42 bar -7") == [42, -7]


def test_ints_none():
    assert ints("no numbers here") == []


def test_ints_single():
    assert ints("100") == [100]


def test_ints_in_sentence():
    assert ints("x=-5,y=10") == [-5, 10]


# --- floats ---

def test_floats_basic():
    result = floats("3.14 2.71")
    assert len(result) == 2
    assert abs(result[0] - 3.14) < 1e-9
    assert abs(result[1] - 2.71) < 1e-9


def test_floats_integers():
    # Integers are also matched as floats
    result = floats("1 2 3")
    assert result == [1.0, 2.0, 3.0]


def test_floats_negative():
    result = floats("-1.5")
    assert result == [-1.5]


# --- words ---

def test_words_basic():
    assert words("hello world") == ["hello", "world"]


def test_words_with_numbers():
    result = words("abc123 def")
    assert "abc123" in result
    assert "def" in result


def test_words_empty():
    assert words("") == []
    assert words("!!! ???") == []


# --- chars ---

def test_chars_basic():
    assert chars("abc") == ["a", "b", "c"]


def test_chars_empty():
    assert chars("") == []


def test_chars_preserves_order():
    result = chars("hello")
    assert result == ["h", "e", "l", "l", "o"]
