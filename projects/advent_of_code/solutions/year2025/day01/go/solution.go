package main

import (
	"fmt"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("advent_of_code/solutions/year2025/day01/input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	lines := aoc.Lines(input)
	pos := 50
	count := 0

	for _, line := range lines {
		if line == "" {
			continue
		}
		dir := line[0]
		dist := aoc.MustInt(line[1:])

		if dir == 'L' {
			pos -= dist
		} else {
			pos += dist
		}
		pos = aoc.Mod(pos, 100)

		if pos == 0 {
			count++
		}
	}

	return count
}

func part2(input string) int {
	lines := aoc.Lines(input)
	pos := 50
	count := 0

	for _, line := range lines {
		if line == "" {
			continue
		}
		dir := line[0]
		dist := aoc.MustInt(line[1:])

		if dir == 'R' {
			count += (pos + dist) / 100
			pos = (pos + dist) % 100
		} else {
			if pos == 0 {
				count += dist / 100
			} else if dist >= pos {
				count += (dist-pos)/100 + 1
			}
			pos = aoc.Mod(pos-dist, 100)
		}
	}

	return count
}
