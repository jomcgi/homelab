#!/usr/bin/env python3
"""Advent of Code 2015 Day 2"""

from projects.advent_of_code.python.aoc import lines, ints, read_file


def part1(input_text: str) -> int:
    total = 0
    for line in lines(input_text):
        l, w, h = ints(line)
        sides = [l * w, w * h, h * l]
        surface_area = 2 * sum(sides)
        extra = min(sides)
        total += surface_area + extra
    return total


def part2(input_text: str) -> int:
    total = 0
    for line in lines(input_text):
        l, w, h = ints(line)
        dimensions = sorted([l, w, h])
        ribbon = 2 * dimensions[0] + 2 * dimensions[1]
        bow = l * w * h
        total += ribbon + bow
    return total


if __name__ == "__main__":
    input_text = read_file("../input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
