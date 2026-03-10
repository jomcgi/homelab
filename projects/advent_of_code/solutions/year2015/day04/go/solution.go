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
	lines := aoc.Lines(input)
	_ = lines
	// TODO: implement
	return 0
}

func part2(input string) int {
	lines := aoc.Lines(input)
	_ = lines
	// TODO: implement
	return 0
}
