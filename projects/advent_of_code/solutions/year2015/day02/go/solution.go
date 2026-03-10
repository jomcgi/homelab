package main

import (
	"fmt"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("../input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	total := 0
	for _, line := range aoc.Lines(input) {
		dims := aoc.Ints(line)
		l, w, h := dims[0], dims[1], dims[2]
		sides := []int{l * w, w * h, h * l}
		surfaceArea := 2 * (sides[0] + sides[1] + sides[2])
		extra := min(sides[0], sides[1], sides[2])
		total += surfaceArea + extra
	}
	return total
}

func part2(input string) int {
	total := 0
	for _, line := range aoc.Lines(input) {
		dims := aoc.Ints(line)
		l, w, h := dims[0], dims[1], dims[2]
		perimeters := []int{2*l + 2*w, 2*w + 2*h, 2*h + 2*l}
		ribbon := min(perimeters[0], perimeters[1], perimeters[2])
		bow := l * w * h
		total += ribbon + bow
	}
	return total
}
