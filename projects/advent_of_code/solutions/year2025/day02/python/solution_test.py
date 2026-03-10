#!/usr/bin/env python3
"""Tests for Advent of Code 2025 Day 2"""

import json
from pathlib import Path

import pytest

from advent_of_code.solutions.year2025.day02.python.solution import part1, part2


@pytest.fixture
def input_text():
    return Path("advent_of_code/solutions/year2025/day02/input.txt").read_text()


@pytest.fixture
def answers():
    answers_path = Path("advent_of_code/solutions/year2025/day02/answers.json")
    if not answers_path.exists():
        pytest.skip("answers.json not found")
    return json.loads(answers_path.read_text())


def test_part1(input_text, answers):
    if "part1" not in answers or answers["part1"] is None:
        pytest.skip("part1 answer not yet verified")

    got = part1(input_text)
    want = int(answers["part1"])
    assert got == want, f"part1() = {got}, want {want}"


def test_part2(input_text, answers):
    if "part2" not in answers or answers["part2"] is None:
        pytest.skip("part2 answer not yet verified")

    got = part2(input_text)
    want = int(answers["part2"])
    assert got == want, f"part2() = {got}, want {want}"
