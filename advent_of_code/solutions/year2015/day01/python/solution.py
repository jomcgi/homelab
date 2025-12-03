#!/usr/bin/env python3
"""Advent of Code 2015 Day 1"""

from advent_of_code.python.aoc import lines, ints, read_file


def part1(input_text: str) -> int:
    floor = 0
    for char in input_text.strip():
        if char == "(":
            floor += 1
        elif char == ")":
            floor -= 1
    return floor


def part2(input_text: str) -> int:
    floor = 0
    for position, char in enumerate(input_text.strip(), start=1):
        if char == "(":
            floor += 1
        elif char == ")":
            floor -= 1
        if floor == -1:
            return position
    return 0


if __name__ == "__main__":
    input_text = read_file("../input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
