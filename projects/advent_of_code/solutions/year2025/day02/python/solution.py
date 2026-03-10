#!/usr/bin/env python3
"""Advent of Code 2025 Day 2"""

from projects.advent_of_code.python.aoc import read_file


def parse_ranges(input_text: str) -> list[tuple[int, int]]:
    """Parse comma-separated ranges from input."""
    ranges = []
    for part in input_text.strip().split(","):
        part = part.strip()
        if part and "-" in part:
            # Split on dash to get start-end (can't use ints() as it treats - as negative)
            start_str, end_str = part.split("-", 1)
            ranges.append((int(start_str), int(end_str)))
    return ranges


def sum_invalid_in_range(start: int, end: int) -> int:
    """Find all 'doubled' numbers (base repeated twice) in [start, end]."""
    total = 0
    for digits in range(1, 11):
        min_base = 1 if digits == 1 else 10 ** (digits - 1)
        max_base = 10**digits - 1
        multiplier = 10**digits + 1  # e.g., for 2 digits: 101

        for base in range(min_base, max_base + 1):
            num = base * multiplier
            if num > end:
                break
            if num >= start:
                total += num
    return total


def sum_invalid_in_range_v2(start: int, end: int) -> int:
    """Find all numbers where a base is repeated 2+ times in [start, end]."""
    seen = set()

    for base_digits in range(1, 11):
        min_base = 1 if base_digits == 1 else 10 ** (base_digits - 1)
        max_base = 10**base_digits - 1

        for reps in range(2, 21):
            # Calculate multiplier: 1 + 10^d + 10^(2d) + ... for reps terms
            multiplier = sum(10 ** (base_digits * r) for r in range(reps))

            min_num = min_base * multiplier
            max_num = max_base * multiplier

            if min_num > end:
                break
            if max_num < start:
                continue

            # Calculate range of bases that produce numbers in [start, end]
            lo_base = max(min_base, (start + multiplier - 1) // multiplier)
            hi_base = min(max_base, end // multiplier)

            for base in range(lo_base, hi_base + 1):
                num = base * multiplier
                if start <= num <= end:
                    seen.add(num)

    return sum(seen)


def part1(input_text: str) -> int:
    ranges = parse_ranges(input_text)
    return sum(sum_invalid_in_range(start, end) for start, end in ranges)


def part2(input_text: str) -> int:
    ranges = parse_ranges(input_text)
    return sum(sum_invalid_in_range_v2(start, end) for start, end in ranges)


if __name__ == "__main__":
    input_text = read_file("advent_of_code/solutions/year2025/day02/input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
