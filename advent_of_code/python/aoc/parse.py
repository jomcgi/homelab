"""Parsing utilities for Advent of Code."""

import re
from pathlib import Path
from typing import Iterator

__all__ = [
    "read_file",
    "read_lines",
    "lines",
    "paragraphs",
    "ints",
    "floats",
    "words",
    "chars",
]


def read_file(path: str | Path) -> str:
    """Read entire file contents, stripping trailing newline."""
    return Path(path).read_text().rstrip("\n")


def read_lines(path: str | Path) -> list[str]:
    """Read file and return list of lines."""
    return read_file(path).split("\n")


def lines(s: str) -> list[str]:
    """Split string into lines."""
    s = s.rstrip("\n")
    if not s:
        return []
    return s.split("\n")


def paragraphs(s: str) -> list[str]:
    """Split string by blank lines (double newlines)."""
    s = s.strip()
    if not s:
        return []
    return s.split("\n\n")


def ints(s: str) -> list[int]:
    """Extract all integers (including negative) from a string."""
    return [int(x) for x in re.findall(r"-?\d+", s)]


def floats(s: str) -> list[float]:
    """Extract all floating point numbers from a string."""
    return [float(x) for x in re.findall(r"-?\d+\.?\d*", s)]


def words(s: str) -> list[str]:
    """Extract all word characters from a string."""
    return re.findall(r"\w+", s)


def chars(s: str) -> list[str]:
    """Split string into individual characters."""
    return list(s)
