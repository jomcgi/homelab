#!/usr/bin/env python3
"""Advent of Code 2025 Day 3"""

from advent_of_code.python.aoc import lines, ints, read_file


def max_joltage(line: str) -> int:
    """Find max 2-digit number by picking 2 digits in order."""
    n = len(line)
    max_val = 0
    for i in range(n - 1):
        first = int(line[i])
        max_second = max(int(line[j]) for j in range(i + 1, n))
        val = first * 10 + max_second
        max_val = max(max_val, val)
    return max_val


def max_joltage_12(line: str) -> int:
    """Find max 12-digit number by picking 12 digits in order."""
    n = len(line)
    keep = 12
    result = 0
    start = 0

    for i in range(keep):
        # Can pick from start to n-keep+i (inclusive)
        end = n - keep + i
        max_digit = "0"
        max_idx = start
        for j in range(start, end + 1):
            if line[j] > max_digit:
                max_digit = line[j]
                max_idx = j
        result = result * 10 + int(max_digit)
        start = max_idx + 1

    return result


def part1(input_text: str) -> int:
    return sum(max_joltage(line) for line in lines(input_text))


def part2(input_text: str) -> int:
    return sum(max_joltage_12(line) for line in lines(input_text))


if __name__ == "__main__":
    input_text = read_file("advent_of_code/solutions/year2025/day03/input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
