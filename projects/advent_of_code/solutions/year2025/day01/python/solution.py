#!/usr/bin/env python3
"""Advent of Code 2025 Day 1"""

from projects.advent_of_code.python.aoc import lines, read_file


def part1(input_text: str) -> int:
    pos = 50
    count = 0
    for line in lines(input_text):
        dir, dist = line[0], int(line[1:])
        if dir == "L":
            pos -= dist
        else:
            pos += dist
        pos = pos % 100
        if pos == 0:
            count += 1
    return count


def part2(input_text: str) -> int:
    pos = 50
    count = 0
    for line in lines(input_text):
        dir, dist = line[0], int(line[1:])
        if dir == "R":
            count += (pos + dist) // 100
            pos = (pos + dist) % 100
        else:
            if pos == 0:
                count += dist // 100
            elif dist >= pos:
                count += (dist - pos) // 100 + 1
            pos = (pos - dist) % 100
    return count


if __name__ == "__main__":
    input_text = read_file("advent_of_code/solutions/year2025/day01/input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
