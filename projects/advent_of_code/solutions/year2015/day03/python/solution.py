#!/usr/bin/env python3
"""Advent of Code 2015 Day 3"""

from projects.advent_of_code.python.aoc import read_file, Point, UP, DOWN, LEFT, RIGHT


def part1(input_text: str) -> int:
    directions = {
        "^": UP,
        "v": DOWN,
        "<": LEFT,
        ">": RIGHT,
    }

    visited = {Point(0, 0)}
    pos = Point(0, 0)

    for char in input_text.strip():
        pos = pos + directions[char]
        visited.add(pos)

    return len(visited)


def part2(input_text: str) -> int:
    directions = {
        "^": UP,
        "v": DOWN,
        "<": LEFT,
        ">": RIGHT,
    }

    visited = {Point(0, 0)}
    santa_pos = Point(0, 0)
    robo_pos = Point(0, 0)

    for i, char in enumerate(input_text.strip()):
        if i % 2 == 0:
            santa_pos = santa_pos + directions[char]
            visited.add(santa_pos)
        else:
            robo_pos = robo_pos + directions[char]
            visited.add(robo_pos)

    return len(visited)


if __name__ == "__main__":
    input_text = read_file("../input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
